"""A directory of JSON files, one per record, with the same refusals as the knowledge store.

`knowledge/company_os/ledger.py` argued this layout at length and the argument
is unchanged here: it diffs, it merges, and it is legible with `cat`. Research
records are if anything a better fit - they are written once by a person, read
by the next person, and their whole value is that a reviewer can see what
changed in a pull request.

```
intelligence/research/records/
    discovery_queries/<id>.json
    discovery_candidates/<id>.json
    public_snapshots/<id>.json
    sources/<id>.json
    references/<id>.json
    opportunities/<id>.json
    video_dossiers/<id>.json
    rubrics/<id>.json
    scorecards/<id>.json
```

The brief's sketch is `sources/ references/ opportunities/`; the `records/`
level is inserted so code and data do not share a directory, matching the
knowledge store.

## Deduplication is a file lookup, not a scan

`public_snapshots/<id>.json` holds a `SnapshotSeries`, and its id is derived
from the content identity. So "have we already got this video?" is opening one
file by name. `ingest()` is built on that: an identity already present merges
into the candidate we hold, an identity absent writes a new one, and two
sessions ingesting the same video in either order finish with one candidate.

## No silent overwrite

`add()` refuses to replace an existing file unless the caller passes
`overwrite=True`. The lifecycle helpers in `lifecycle.py` return new records
and the caller re-writes them deliberately - a stage change is an edit to the
thread, and it is *visible* as one in git. What the store refuses is the
accidental case: two threads that chose the same id, or a re-run of a script
that quietly replaces yesterday's analysis.

## Integrity is cross-record, and structural only

A record validates itself at construction. What it cannot check is whether the
ids it points at exist, and that is what `integrity()` is for: dangling links
in both directions, scorecards against rubrics that do not define their
dimensions, and reference cases whose source is gone.

It does not check whether an analysis is *good*, or whether two opportunity
statements contradict each other. `KnowledgeStore.contradictions` draws the
same line for the same reason - that is a reasoning task, and this is the
deterministic half.

## Staleness

Every research record carries a `ResearchConfidence` with a freshness class and
a recheck date, so a sweep for expired research is the same arithmetic the
knowledge store uses. `stale()` takes `today`; the clock is read in one place
and only when the caller supplies nothing.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ai_platform.serde import read_json, write_json
from intelligence.research.batch import (
    BatchStatus,
    DiscoveryRound,
    ResearchBatch,
)
from intelligence.research.batch_control import (
    BatchProgress,
    StopSignal,
    advance_batch,
    escalate_batch,
    evaluate_stop_conditions,
    exceeded_limits,
    record_round,
    stop_batch,
)
from intelligence.research.batch_metrics import (
    CandidateOutcome,
    batch_progress,
    outcome_of,
    round_progress,
    saturation_signals,
)
from intelligence.research.batch_report import BatchReport, build_batch_report
from intelligence.research.discovery import (
    CandidateState,
    DiscoveryCandidate,
    DiscoveryQuery,
    candidate_conflicts,
    merge_candidates,
)
from intelligence.research.errors import ResearchError
from intelligence.research.opportunity import OpportunityDossier
from intelligence.research.promotion import PromotionResult, promote_candidate
from intelligence.research.reference_case import ReferenceCase
from intelligence.research.resources import ResearchResourceRecord
from intelligence.research.scoring import OpportunityScorecard, ScoringRubric
from intelligence.research.screening_queue import (
    QueueEntry,
    ScreeningAssessment,
    screening_queue,
)
from intelligence.research.snapshots import PublicSnapshot, SnapshotSeries, series_id
from intelligence.research.sources import ResearchSource
from intelligence.research.urls import ContentIdentity
from intelligence.research.video_dossier import VideoIntelligenceDossier
from knowledge.company_os.freshness import is_stale

DEFAULT_ROOT = Path(__file__).resolve().parent / "records"

RECORD_TYPES: dict[str, type] = {
    DiscoveryQuery.kind: DiscoveryQuery,
    DiscoveryCandidate.kind: DiscoveryCandidate,
    SnapshotSeries.kind: SnapshotSeries,
    ResearchSource.kind: ResearchSource,
    ReferenceCase.kind: ReferenceCase,
    OpportunityDossier.kind: OpportunityDossier,
    VideoIntelligenceDossier.kind: VideoIntelligenceDossier,
    ScoringRubric.kind: ScoringRubric,
    OpportunityScorecard.kind: OpportunityScorecard,
    ResearchBatch.kind: ResearchBatch,
    ScreeningAssessment.kind: ScreeningAssessment,
    ResearchResourceRecord.kind: ResearchResourceRecord,
}

DIRECTORIES: dict[str, str] = {
    DiscoveryQuery.kind: "discovery_queries",
    DiscoveryCandidate.kind: "discovery_candidates",
    SnapshotSeries.kind: "public_snapshots",
    ResearchSource.kind: "sources",
    ReferenceCase.kind: "references",
    OpportunityDossier.kind: "opportunities",
    VideoIntelligenceDossier.kind: "video_dossiers",
    ScoringRubric.kind: "rubrics",
    OpportunityScorecard.kind: "scorecards",
    ResearchBatch.kind: "research_batches",
    ScreeningAssessment.kind: "screening_assessments",
    ResearchResourceRecord.kind: "research_resources",
}


@dataclass(frozen=True)
class IntegrityIssue:
    """One thing a record could not have noticed about itself."""

    kind: str
    record_id: str
    problem: str

    def __str__(self) -> str:
        return f"{self.kind}/{self.record_id}: {self.problem}"


@dataclass(frozen=True)
class IngestionOutcome:
    """What one ingestion did, said plainly enough for a CLI to print it.

    `merged` is the number the funnel cares about. A high merge rate means the
    queries overlap, which is information about the queries; it also means the
    dedupe is earning its place, because every merge is an analysis not bought
    twice.
    """

    candidate: DiscoveryCandidate
    series: SnapshotSeries
    merged: bool
    snapshot_added: bool
    conflicts: tuple[str, ...] = ()

    @property
    def action(self) -> str:
        return "merged" if self.merged else "added"


class ResearchStore:
    """Research records, addressed by (kind, id)."""

    def __init__(self, root: Path | str = DEFAULT_ROOT) -> None:
        self.root = Path(root)

    def path_for(self, kind: str, record_id: str) -> Path:
        if kind not in RECORD_TYPES:
            raise ResearchError(
                f"unknown research record kind {kind!r}; expected one of {sorted(RECORD_TYPES)}"
            )
        return self.root / DIRECTORIES[kind] / f"{record_id}.json"

    def add(self, record: Any, *, overwrite: bool = False) -> Path:
        """Write a record. Refuses to replace one silently."""
        kind = getattr(record, "kind", None)
        if kind not in RECORD_TYPES:
            raise ResearchError(f"not a research record: {type(record).__name__}")
        path = self.path_for(kind, record.id)
        if path.exists() and not overwrite:
            raise ResearchError(
                f"{kind}/{record.id} already exists. Write a new record that cites it, "
                "or pass overwrite=True if you are deliberately updating this one."
            )
        return write_json(path, record)

    def get(self, kind: str, record_id: str) -> Any:
        path = self.path_for(kind, record_id)
        if not path.exists():
            raise ResearchError(f"no {kind} record {record_id!r} at {path}")
        return RECORD_TYPES[kind].from_dict(read_json(path))

    def exists(self, kind: str, record_id: str) -> bool:
        return self.path_for(kind, record_id).exists()

    def load_all(self, kind: str | None = None) -> tuple[Any, ...]:
        """Every record, or every record of one kind, in a stable order."""
        kinds = [kind] if kind else sorted(RECORD_TYPES)
        if kind is not None and kind not in RECORD_TYPES:
            raise ResearchError(f"unknown research record kind {kind!r}")
        out: list[Any] = []
        for k in kinds:
            directory = self.root / DIRECTORIES[k]
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.json")):
                out.append(RECORD_TYPES[k].from_dict(read_json(path)))
        return tuple(out)

    def ids(self, kind: str) -> frozenset[str]:
        directory = self.root / DIRECTORIES[kind]
        if not directory.is_dir():
            return frozenset()
        return frozenset(p.stem for p in directory.glob("*.json"))

    # -- discovery --------------------------------------------------------

    def series_for(self, identity: ContentIdentity) -> SnapshotSeries | None:
        """The series for one piece of content, or None. One file lookup."""
        record_id = series_id(identity)
        if not self.exists(SnapshotSeries.kind, record_id):
            return None
        return self.get(SnapshotSeries.kind, record_id)

    def candidate_for(self, identity: ContentIdentity) -> DiscoveryCandidate | None:
        """The candidate already holding this content, or None.

        Resolved through the series rather than by scanning titles: a title is
        not an identity, and two videos share one every week.
        """
        series = self.series_for(identity)
        if series is None:
            return None
        for candidate_id in series.candidate_ids:
            if self.exists(DiscoveryCandidate.kind, candidate_id):
                return self.get(DiscoveryCandidate.kind, candidate_id)
        return None

    def ingest(
        self,
        candidate: DiscoveryCandidate,
        snapshot: PublicSnapshot | None = None,
    ) -> IngestionOutcome:
        """Add a candidate, or fold it into the one we already hold.

        The deduplication rule, in one place: identity first, canonical URL as
        the fallback identity, and never the title. A second sighting adds its
        discovery provenance and its reading; it does not reset screening, and
        it does not overwrite a field the first sighting already filled.
        """
        identity = candidate.identity
        existing = self.candidate_for(identity)
        merged = existing is not None
        conflicts: tuple[str, ...] = ()
        if existing is not None:
            conflicts = candidate_conflicts(existing, candidate)
            candidate = merge_candidates(existing, candidate)

        series = self.series_for(identity) or SnapshotSeries.for_identity(identity)
        series = series.watching(candidate_id=candidate.id)
        snapshot_added = False
        if snapshot is not None and not any(s.key == snapshot.key for s in series.snapshots):
            series = series.add(snapshot)
            snapshot_added = True

        # overwrite=True is deliberate on both: a merge is an edit to a record
        # this method just read, and it shows up in git as the lines that moved.
        self.add(candidate, overwrite=True)
        self.add(series, overwrite=True)
        return IngestionOutcome(
            candidate=candidate,
            series=series,
            merged=merged,
            snapshot_added=snapshot_added,
            conflicts=conflicts,
        )

    def candidates(self, state: CandidateState | None = None) -> tuple[DiscoveryCandidate, ...]:
        records = self.load_all(DiscoveryCandidate.kind)
        if state is None:
            return records
        return tuple(c for c in records if c.state is state)

    def promote(self, candidate_id: str, **kwargs: Any) -> PromotionResult:
        """Promote a screened-in candidate, writing all three records it touches.

        The judgement arguments - confidence, rights, source type - are the
        caller's and have no defaults here worth having. See
        `promotion.promote_candidate` for the refusals.
        """
        candidate = self.get(DiscoveryCandidate.kind, candidate_id)
        result = promote_candidate(candidate, series=self.series_for(candidate.identity), **kwargs)
        self.add(result.source)
        self.add(result.candidate, overwrite=True)
        if result.series is not None:
            self.add(result.series, overwrite=True)
        return result

    # -- batches ----------------------------------------------------------

    def batches(self, status: BatchStatus | None = None) -> tuple[ResearchBatch, ...]:
        records = self.load_all(ResearchBatch.kind)
        if status is None:
            return records
        return tuple(b for b in records if b.status is status)

    def batch_outcomes(self, batch: ResearchBatch) -> tuple[CandidateOutcome, ...]:
        """Join each of the batch's candidates with the source it became.

        The one place the join happens. A candidate id the store does not hold is
        skipped rather than faked - `integrity()` reports it as dangling, and the
        batch report counts it in `unmatched_candidates` so every metric drawn
        from the candidate records carries its own coverage.
        """
        out: list[CandidateOutcome] = []
        for candidate_id in batch.candidate_ids:
            if not self.exists(DiscoveryCandidate.kind, candidate_id):
                continue
            candidate = self.get(DiscoveryCandidate.kind, candidate_id)
            source = None
            if candidate.promoted_source_id and self.exists(
                ResearchSource.kind, candidate.promoted_source_id
            ):
                source = self.get(ResearchSource.kind, candidate.promoted_source_id)
            out.append(outcome_of(candidate, source))
        return tuple(out)

    def batch_assessments(self, batch_id: str) -> tuple[ScreeningAssessment, ...]:
        return tuple(
            a
            for a in self.load_all(ScreeningAssessment.kind)
            if a.batch_id == batch_id
        )

    def batch_resources(self, batch_id: str) -> tuple[ResearchResourceRecord, ...]:
        return tuple(
            r
            for r in self.load_all(ResearchResourceRecord.kind)
            if r.batch_id == batch_id
        )

    def batch_progress(self, batch_id: str) -> BatchProgress:
        batch = self.get(ResearchBatch.kind, batch_id)
        return batch_progress(batch, self.batch_outcomes(batch))

    def batch_stop_signals(
        self, batch_id: str, *, on: dt.date | None = None
    ) -> tuple[StopSignal, ...]:
        """Evaluate the batch's declared conditions. Reports; changes nothing."""
        batch = self.get(ResearchBatch.kind, batch_id)
        outcomes = self.batch_outcomes(batch)
        signals = saturation_signals(batch, round_progress(batch, outcomes))
        return evaluate_stop_conditions(
            batch,
            batch_progress(batch, outcomes),
            on=on or dt.date.today(),
            saturation=signals,
        )

    def batch_queue(self, batch_id: str) -> tuple[QueueEntry, ...]:
        batch = self.get(ResearchBatch.kind, batch_id)
        outcomes = self.batch_outcomes(batch)
        return screening_queue(
            tuple((o.candidate_id, o.state) for o in outcomes),
            self.batch_assessments(batch_id),
        )

    def batch_report(self, batch_id: str, as_of: dt.date | None = None) -> BatchReport:
        """Assemble the whole report from the store. Reads; writes nothing."""
        batch = self.get(ResearchBatch.kind, batch_id)
        return build_batch_report(
            batch,
            self.batch_outcomes(batch),
            self.batch_assessments(batch_id),
            self.batch_resources(batch_id),
            as_of=as_of or dt.date.today(),
        )

    def record_round(
        self, batch_id: str, round: DiscoveryRound, *, by: str, detail: str = ""
    ) -> ResearchBatch:
        """Append a round and write the batch back. Supplies the saturation signals.

        `overwrite=True` is deliberate and is the same call `ingest` makes: this
        is an edit to a record the method has just read, and it shows up in git
        as the lines that moved. What the store still refuses is the accidental
        overwrite - a second batch claiming an id that already exists.
        """
        batch = self.get(ResearchBatch.kind, batch_id)
        outcomes = self.batch_outcomes(batch)
        updated = record_round(
            batch,
            round,
            by=by,
            detail=detail,
            saturation=saturation_signals(batch, round_progress(batch, outcomes)),
        )
        self.add(updated, overwrite=True)
        return updated

    def advance_batch(
        self, batch_id: str, to: BatchStatus, *, on: dt.date, by: str, reason: str
    ) -> ResearchBatch:
        """Move a batch, supplying the evidence its next status requires."""
        batch = self.get(ResearchBatch.kind, batch_id)
        outcomes = self.batch_outcomes(batch)
        progress = batch_progress(batch, outcomes)
        signals = evaluate_stop_conditions(
            batch,
            progress,
            on=on,
            saturation=saturation_signals(batch, round_progress(batch, outcomes)),
        )
        updated = advance_batch(
            batch, to, on=on, by=by, reason=reason, progress=progress, signals=signals
        )
        self.add(updated, overwrite=True)
        return updated

    def stop_batch(
        self, batch_id: str, *, on: dt.date, by: str, reason: str
    ) -> ResearchBatch:
        """Stop a batch, recording which declared condition fired first."""
        batch = self.get(ResearchBatch.kind, batch_id)
        updated = stop_batch(
            batch,
            on=on,
            by=by,
            reason=reason,
            signals=self.batch_stop_signals(batch_id, on=on),
        )
        self.add(updated, overwrite=True)
        return updated

    def escalate_batch(self, batch_id: str, **kwargs: Any) -> ResearchBatch:
        """Authorise continuing. See `batch.escalate_batch` for the refusals."""
        updated = escalate_batch(self.get(ResearchBatch.kind, batch_id), **kwargs)
        self.add(updated, overwrite=True)
        return updated

    def stale(self, today: dt.date | None = None, kind: str | None = None) -> tuple[Any, ...]:
        """Records whose confidence is past its recheck date, soonest due first.

        Rubrics carry no confidence - they are configuration, not a finding -
        and are skipped.
        """
        when = today or dt.date.today()
        return stale_records(self.load_all(kind), when)

    def integrity(self) -> tuple[IntegrityIssue, ...]:
        """Dangling links and mismatched rubrics, in a stable order."""
        issues: list[IntegrityIssue] = []
        source_ids = self.ids(ResearchSource.kind)
        reference_ids = self.ids(ReferenceCase.kind)
        opportunity_ids = self.ids(OpportunityDossier.kind)
        query_ids = self.ids(DiscoveryQuery.kind)
        candidate_ids = self.ids(DiscoveryCandidate.kind)
        series_ids = self.ids(SnapshotSeries.kind)
        rubrics = {r.id: r for r in self.load_all(ScoringRubric.kind)}

        def check(record: Any, field: str, known: frozenset[str], target: str) -> None:
            for value in getattr(record, field, ()):
                if value not in known:
                    issues.append(
                        IntegrityIssue(record.kind, record.id, f"{field} names unknown {target} {value!r}")
                    )

        # One identity, one candidate. A second candidate for content we already
        # hold is the deduplication failing, and it is invisible from inside
        # either record - which is exactly what this sweep is for.
        by_identity: dict[str, list[str]] = {}
        for candidate in self.load_all(DiscoveryCandidate.kind):
            by_identity.setdefault(candidate.identity.key, []).append(candidate.id)
            check(candidate, "query_ids", query_ids, "discovery query")
            if candidate.series_id not in series_ids:
                issues.append(
                    IntegrityIssue(
                        candidate.kind,
                        candidate.id,
                        f"has no snapshot series {candidate.series_id!r}, so it is "
                        "absent from the deduplication index",
                    )
                )
            if candidate.promoted_source_id and candidate.promoted_source_id not in source_ids:
                issues.append(
                    IntegrityIssue(
                        candidate.kind,
                        candidate.id,
                        f"promoted_source_id names unknown source "
                        f"{candidate.promoted_source_id!r}",
                    )
                )
        for key, ids in by_identity.items():
            if len(ids) > 1:
                for duplicate in ids:
                    issues.append(
                        IntegrityIssue(
                            DiscoveryCandidate.kind,
                            duplicate,
                            f"shares content {key!r} with {len(ids) - 1} other "
                            "candidate(s); one identity is one candidate",
                        )
                    )

        for series in self.load_all(SnapshotSeries.kind):
            check(series, "candidate_ids", candidate_ids, "discovery candidate")
            check(series, "source_ids", source_ids, "source")

        for source in self.load_all(ResearchSource.kind):
            check(source, "reference_case_ids", reference_ids, "reference case")
            check(source, "opportunity_ids", opportunity_ids, "opportunity")
            if source.origin is not None and source.origin.candidate_id not in candidate_ids:
                issues.append(
                    IntegrityIssue(
                        source.kind,
                        source.id,
                        f"origin names unknown discovery candidate "
                        f"{source.origin.candidate_id!r}",
                    )
                )

        for case in self.load_all(ReferenceCase.kind):
            if case.source_id not in source_ids:
                issues.append(
                    IntegrityIssue(
                        case.kind, case.id, f"source_id names unknown source {case.source_id!r}"
                    )
                )

        for opportunity in self.load_all(OpportunityDossier.kind):
            check(opportunity, "source_ids", source_ids, "source")
            check(opportunity, "reference_case_ids", reference_ids, "reference case")

        for dossier in self.load_all(VideoIntelligenceDossier.kind):
            check(dossier, "reference_case_ids", reference_ids, "reference case")
            check(dossier, "opportunity_ids", opportunity_ids, "opportunity")

        for card in self.load_all(OpportunityScorecard.kind):
            if card.opportunity_id not in opportunity_ids:
                issues.append(
                    IntegrityIssue(
                        card.kind,
                        card.id,
                        f"opportunity_id names unknown opportunity {card.opportunity_id!r}",
                    )
                )
            rubric = rubrics.get(card.rubric_id)
            if rubric is None:
                issues.append(
                    IntegrityIssue(
                        card.kind, card.id, f"rubric_id names unknown rubric {card.rubric_id!r}"
                    )
                )
                continue
            for extra in sorted(set(card.by_dimension()) - set(rubric.names)):
                issues.append(
                    IntegrityIssue(
                        card.kind,
                        card.id,
                        f"scores {extra!r}, which rubric {rubric.id!r} does not define",
                    )
                )

        issues.extend(self._batch_issues(query_ids, candidate_ids))
        return tuple(sorted(issues, key=lambda i: (i.kind, i.record_id, i.problem)))

    def _batch_issues(
        self, query_ids: frozenset[str], candidate_ids: frozenset[str]
    ) -> tuple[IntegrityIssue, ...]:
        """What a batch, an assessment and a resource record cannot notice alone.

        The one worth having is the provenance cross-check. A batch's round log
        and a candidate's own provenance are two records of the same event
        written by two different calls, and nothing inside either notices when
        they disagree - a candidate charged to a batch whose query never found it
        makes that query look productive and hides which one actually paid.
        """
        issues: list[IntegrityIssue] = []
        batches = self.load_all(ResearchBatch.kind)
        batch_ids = {batch.id for batch in batches}

        sources = self.load_all(ResearchSource.kind)
        promoted_from: dict[str, str] = {
            source.origin.candidate_id: source.id
            for source in sources
            if source.origin is not None
        }

        for batch in batches:
            for query_id in batch.query_ids:
                if query_id not in query_ids:
                    issues.append(
                        IntegrityIssue(
                            batch.kind,
                            batch.id,
                            f"declares unknown discovery query {query_id!r}",
                        )
                    )
            for entry in batch.rounds:
                for candidate_id in entry.observed:
                    if candidate_id not in candidate_ids:
                        issues.append(
                            IntegrityIssue(
                                batch.kind,
                                batch.id,
                                f"a {entry.ran_on} round observed unknown candidate "
                                f"{candidate_id!r}",
                            )
                        )
                        continue
                    candidate = self.get(DiscoveryCandidate.kind, candidate_id)
                    if entry.query_id not in candidate.query_ids:
                        issues.append(
                            IntegrityIssue(
                                batch.kind,
                                batch.id,
                                f"charges candidate {candidate_id!r} to query "
                                f"{entry.query_id!r}, which is not in that candidate's "
                                "provenance",
                            )
                        )

            outcomes = self.batch_outcomes(batch)
            claimed = sum(1 for outcome in outcomes if outcome.is_promoted)
            held = sum(
                1
                for candidate_id in batch.candidate_ids
                if candidate_id in promoted_from
            )
            if claimed != held:
                issues.append(
                    IntegrityIssue(
                        batch.kind,
                        batch.id,
                        f"{claimed} candidate(s) say they were promoted, but {held} "
                        "source(s) in the store name a candidate of this batch as their "
                        "origin",
                    )
                )

            over = exceeded_limits(batch.budget, batch_progress(batch, outcomes))
            if (
                over
                and batch.status not in (BatchStatus.STOPPED, BatchStatus.ARCHIVED)
                and not batch.escalated_since_stop
            ):
                issues.append(
                    IntegrityIssue(
                        batch.kind,
                        batch.id,
                        f"is {batch.status.value!r} having spent past "
                        f"{', '.join(over)}; a breached ceiling stops the batch or is "
                        "escalated by a named authoriser",
                    )
                )

        for assessment in self.load_all(ScreeningAssessment.kind):
            if assessment.batch_id not in batch_ids:
                issues.append(
                    IntegrityIssue(
                        assessment.kind,
                        assessment.id,
                        f"names unknown research batch {assessment.batch_id!r}",
                    )
                )
            elif assessment.candidate_id not in set(
                self.get(ResearchBatch.kind, assessment.batch_id).candidate_ids
            ):
                issues.append(
                    IntegrityIssue(
                        assessment.kind,
                        assessment.id,
                        f"screens candidate {assessment.candidate_id!r}, which batch "
                        f"{assessment.batch_id!r} never observed",
                    )
                )
            if assessment.candidate_id not in candidate_ids:
                issues.append(
                    IntegrityIssue(
                        assessment.kind,
                        assessment.id,
                        f"names unknown discovery candidate "
                        f"{assessment.candidate_id!r}",
                    )
                )

        for record in self.load_all(ResearchResourceRecord.kind):
            if record.batch_id not in batch_ids:
                issues.append(
                    IntegrityIssue(
                        record.kind,
                        record.id,
                        f"charges {record.batch_id!r}, which is not a research batch",
                    )
                )

        return tuple(issues)

    def thread(self, source_id: str) -> dict[str, tuple[Any, ...]]:
        """One source and everything downstream of it, for a reviewer.

        The evidence package the brief asks the workflow to produce: the source,
        its reference cases, its opportunities, and the scorecards on those.
        """
        source = self.get(ResearchSource.kind, source_id)
        cases = tuple(
            self.get(ReferenceCase.kind, rid)
            for rid in source.reference_case_ids
            if self.exists(ReferenceCase.kind, rid)
        )
        opportunities = tuple(
            self.get(OpportunityDossier.kind, oid)
            for oid in source.opportunity_ids
            if self.exists(OpportunityDossier.kind, oid)
        )
        opportunity_ids = {o.id for o in opportunities}
        cards = tuple(
            c
            for c in self.load_all(OpportunityScorecard.kind)
            if c.opportunity_id in opportunity_ids
        )
        # The discovery half of the thread, when the source came through the
        # queue: which query found it, and every public reading since.
        candidates: tuple[Any, ...] = ()
        series: tuple[Any, ...] = ()
        if source.origin is not None:
            if self.exists(DiscoveryCandidate.kind, source.origin.candidate_id):
                candidates = (self.get(DiscoveryCandidate.kind, source.origin.candidate_id),)
            found = self.series_for(
                ContentIdentity(
                    platform=source.origin.platform,
                    external_id=source.origin.external_id,
                    canonical_url=source.origin.canonical_url,
                )
            )
            if found is not None:
                series = (found,)
        return {
            "source": (source,),
            "candidates": candidates,
            "snapshot_series": series,
            "reference_cases": cases,
            "opportunities": opportunities,
            "scorecards": cards,
        }


def stale_records(records: Iterable[Any], today: dt.date) -> tuple[Any, ...]:
    """Filter records to those whose confidence is past its recheck date. Pure."""
    out = []
    for record in records:
        confidence = getattr(record, "confidence", None)
        if confidence is None:
            continue
        if is_stale(
            confidence.freshness, confidence.observed_on, confidence.recheck_on, today
        ):
            out.append(record)
    out.sort(key=lambda r: (r.confidence.recheck_on or r.confidence.observed_on, r.kind, r.id))
    return tuple(out)
