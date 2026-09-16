"""A directory of JSON files, one per record, with the same refusals as the knowledge store.

`knowledge/company_os/ledger.py` argued this layout at length and the argument
is unchanged here: it diffs, it merges, and it is legible with `cat`. Research
records are if anything a better fit - they are written once by a person, read
by the next person, and their whole value is that a reviewer can see what
changed in a pull request.

```
intelligence/research/records/
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
from intelligence.research.errors import ResearchError
from intelligence.research.opportunity import OpportunityDossier
from intelligence.research.reference_case import ReferenceCase
from intelligence.research.scoring import OpportunityScorecard, ScoringRubric
from intelligence.research.sources import ResearchSource
from intelligence.research.video_dossier import VideoIntelligenceDossier
from knowledge.company_os.freshness import is_stale

DEFAULT_ROOT = Path(__file__).resolve().parent / "records"

RECORD_TYPES: dict[str, type] = {
    ResearchSource.kind: ResearchSource,
    ReferenceCase.kind: ReferenceCase,
    OpportunityDossier.kind: OpportunityDossier,
    VideoIntelligenceDossier.kind: VideoIntelligenceDossier,
    ScoringRubric.kind: ScoringRubric,
    OpportunityScorecard.kind: OpportunityScorecard,
}

DIRECTORIES: dict[str, str] = {
    ResearchSource.kind: "sources",
    ReferenceCase.kind: "references",
    OpportunityDossier.kind: "opportunities",
    VideoIntelligenceDossier.kind: "video_dossiers",
    ScoringRubric.kind: "rubrics",
    OpportunityScorecard.kind: "scorecards",
}


@dataclass(frozen=True)
class IntegrityIssue:
    """One thing a record could not have noticed about itself."""

    kind: str
    record_id: str
    problem: str

    def __str__(self) -> str:
        return f"{self.kind}/{self.record_id}: {self.problem}"


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
        rubrics = {r.id: r for r in self.load_all(ScoringRubric.kind)}

        def check(record: Any, field: str, known: frozenset[str], target: str) -> None:
            for value in getattr(record, field, ()):
                if value not in known:
                    issues.append(
                        IntegrityIssue(record.kind, record.id, f"{field} names unknown {target} {value!r}")
                    )

        for source in self.load_all(ResearchSource.kind):
            check(source, "reference_case_ids", reference_ids, "reference case")
            check(source, "opportunity_ids", opportunity_ids, "opportunity")

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

        return tuple(sorted(issues, key=lambda i: (i.kind, i.record_id, i.problem)))

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
        return {
            "source": (source,),
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
