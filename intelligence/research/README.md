# Company OS research & intelligence

Twelve record types, a discovery queue, a budgeted batch in front of it, one
seven-stage workflow, and a directory of JSON files. No database, no
embeddings, no network. Everything here is `dataclasses` and `json`, same as
the knowledge store it sits beside.

This layer stores and evaluates research. It does not go and get it: there is
no scraper, no API client, no browser driver, no downloader and no model. That
is deliberate and it is the sequencing in `docs/company_os_v1_bootstrap.md` —
the contracts prove stable first, and automated discovery is built against a
schema that already works. The ingestion boundary below is the shape any future
connector has to produce; today a researcher produces it by hand.

## Knowledge capsule ownership

`company-research-intelligence` is authoritative for the core research
contracts: `ResearchSource`, `ReferenceCase`, `OpportunityDossier`,
`VideoIntelligenceDossier`, scoring, and their core invariants.
`company-research-operations` is authoritative for ingestion, discovery,
public snapshots, screening, research batches, resource accounting,
saturation, and stop rules. The operations capsule hands screened evidence to
the core contracts; it does not redefine them.

## Where records live

```
intelligence/research/records/
    discovery_queries/<id>.json
    discovery_candidates/<id>.json
    public_snapshots/<id>.json
    research_batches/<id>.json
    screening_assessments/<id>.json
    research_resources/<id>.json
    sources/<id>.json
    references/<id>.json
    opportunities/<id>.json
    video_dossiers/<id>.json
    rubrics/<id>.json
    scorecards/<id>.json
```

`<id>` is lowercase `[a-z0-9._-]`, because it is also the filename. Files are
written with sorted keys, so two sessions writing different records never
conflict and a research change shows up in `git diff` as the sentence that
changed.

## The twelve types

| Type | Answers | Required beyond the common fields |
|---|---|---|
| `ResearchSource` | What did we find, and what may we keep of it? | `reference`, `rights`, `confidence` |
| `ReferenceCase` | What does it teach, and where is the line? | nine sections, all of them, incl. `originality` |
| `OpportunityDossier` | What could we make, and why do we believe it? | `evidence` (≥1), `limitations` (≥1), `format_class` |
| `VideoIntelligenceDossier` | What is this video testing? | `experiment`, `kill_conditions` (≥1), `superiority_targets` (≥1) |
| `ScoringRubric` | What are we weighing, and how heavily? | `dimensions` (≥1), explicit weights |
| `OpportunityScorecard` | What did a researcher judge, and why? | `scores` (≥1), each with a `reason` |
| `DiscoveryQuery` | What did we go looking for? | `terms` (≥1), `objective`, a known `platform` |
| `DiscoveryCandidate` | What turned up, and has anyone judged it? | `provenance` (≥1), `evidence`, `capture_method` |
| `SnapshotSeries` | What did the public page show, and when? | a derived `id`, snapshots oldest first |
| `ResearchBatch` | How much are we allowed to spend on this search? | `budget`, `stop_conditions` (>=1), `query_ids` (>=1) |
| `ScreeningAssessment` | What did a screener think, and on what? | `reason`, `evidence` (>=1), a reviewer and a date |
| `ResearchResourceRecord` | What did this cost, and at which tier? | a `CostTier` and at least one measurement |

Common to most: `id`, `created`, an author, and a `ResearchConfidence`. The
three discovery types carry no confidence: a candidate is a URL and some public
counts, and asking a screener to rate their belief in forty of those would cost
more than reading them.

## The discovery queue, before any of that

A `ReferenceCase` costs an analyst an afternoon; a `DiscoveryCandidate` costs a
URL. The queue in front of the workflow exists so that most candidates never
reach the afternoon.

```
DiscoveryQuery -> IngestionEnvelope -> DiscoveryCandidate -> screening -> ResearchSource
```

as states on the candidate:

```
DISCOVERED -> QUEUED -> SCREENED_IN -> PROMOTED_TO_SOURCE
           \-> SCREENED_OUT                \-> ARCHIVED
```

**One video is one candidate.** Every URL is reduced to a `ContentIdentity` -
`platform` plus external id - so `youtu.be/ID`, `/watch?v=ID&t=42`,
`/shorts/ID`, `/embed/ID` and `/live/ID` are one row, not five. Identity never
falls back to the title, because two different videos share one every week.
Deduplication is a file lookup: `public_snapshots/<id>.json` is named after the
identity, so "have we got this?" opens one file.

**A second sighting adds, it never replaces.** Re-discovery unions the
provenance, so a video found by three queries keeps all three - that several
found it is a signal no single query can see. It fills fields that were blank,
leaves fields that were not, reports the disagreement through
`candidate_conflicts`, and does not touch the screening state. A scheduled
query cannot resurrect a rejected candidate.

**A person screens.** There is no `auto_screen`, and `screen_candidate` takes a
reviewer, a reason and a date. `excluded_by` and `within_freshness` report facts
about the researcher's own query and change no state.

**Only a screened-in candidate promotes.** `promote_candidate` is the single
path to a `ResearchSource`, and it refuses a screened-out one outright. The
source keeps the canonical URL as its reference and a `DiscoveryOrigin` holding
the string the researcher actually clicked, the capture method, and every query
that found it. It arrives at `SCREENED` rather than `DISCOVERED`, because the
screener already made that judgement once.

## Ingestion: one door, no network

An `IngestionEnvelope` is platform, URL, capture date, capture method, evidence
pointer and payload. The payload is checked against a per-platform schema:

- an unknown key is **refused**, not dropped - a silently dropped field is a
  metric somebody believes they recorded;
- a private channel analytic is **refused by name**: retention, average
  percentage viewed, revenue, RPM, CPM, impressions, traffic sources,
  subscriber conversion. No public page shows them for somebody else's video;
- a count that arrived as `"1.2M"` fails at the boundary rather than becoming a
  float three modules later.

There is no payload key naming a file, a download or a local copy, so the
ingestion path cannot satisfy `RightsStatus`'s copy requirements at all.

The one shipped adapter reads a JSON file a researcher wrote by hand. That is
the cheap path, it works today, and every future connector - browser extension,
API export, partner feed - produces the same envelope.

## Snapshots: an observation is not an update

A view count is a property of a video *on a day*. Writing a new number over the
old one destroys the only thing two readings are good for. So `SnapshotSeries`
appends, a reading already recorded is refused rather than merged, and
`growth_between` names every rate it could not compute and why: no views/day
across two readings on the same day, no likes gained when one reading did not
show likes.

## The cost tiers

```
T0 identity  T1 public metadata  T2 screening
T3 reference analysis  T4 opportunity dossier  T5 prototype recommendation
```

`funnel.py` describes them and executes none of them. A tier is *derived* from
a state that already exists - `CandidateState` or `ResearchStage` - so it
cannot drift from the record it describes. `next_tier` returns a description;
nothing in this package calls it in a loop, because the gap between two tiers
is where a person decides whether the next one is worth paying for.

## Batches: how much of this are we allowed to buy?

A query can return four results or four hundred, and the cost of four hundred is
not in holding them - it is in the afternoon each one can ask for. A
`ResearchBatch` is one search with a ceiling on that.

```
plan (budget + stop conditions) -> collecting -> screening -> analysis_ready
                                        \-> stopped -> escalated -> collecting
```

**The conditions are written before the collecting.** A batch requires at least
one `StopCondition` at construction. A stop rule chosen after the numbers are in
is not a rule, it is a description of where somebody happened to stop, and it
cannot fail. Six reasons - unique candidates, observations, queries, budget,
saturation, deadline - and each carries exactly the parameter it needs and
refuses the others.

**A round is refused whole, never trimmed.** `record_round` checks the three
collection ceilings and rejects a round that would cross one, naming the limit
and both remedies. Truncating the round to fit would lose evidence silently, and
would make the duplicate rate wrong in a direction nobody could see.

**A fired condition stops collecting; an exceeded ceiling stops everything.**
Those are different rules on purpose. Reaching `max_unique_candidates` is the
ceiling *working* - the next thing the batch should do is screen what it found -
so a fired condition blocks the way back into `COLLECTING` and blocks
`record_round`, and nothing else. *Exceeding* any ceiling is spend nobody
authorised, and it blocks every forward move until `escalate_batch` raises it
with an authoriser's name in the history.

`batch.py` is what a batch is; `batch_control.py` is the four functions that
change one, each refused against a measurement; `batch_metrics.py` is the pure
arithmetic over the round log and the candidate records.

**The round log is the measurement.** `rounds` is append-only and chronological;
`candidate_ids` is a derived property, so there is no second list to disagree
with it. Saturation, duplication and query contribution are all replays of that
log, which is why "new" means new *at that point*.

### What the numbers refuse to say

| Question | Answer when nobody measured it |
|---|---|
| new-candidate rate for a round that observed nothing | `None` - "the round observed nothing", not 0.0 |
| new-creator rate where no observation named a creator | `None`, and the saturation verdict becomes `INSUFFICIENT_EVIDENCE` |
| top-creator share with no creator recorded | `None`; the share otherwise divides by the *known* creators and prints the unknown count |
| mechanics observed | only explicit `tags`. No tokenizer, no title parsing |
| saturation over fewer rounds than the rule wants | `INSUFFICIENT_EVIDENCE` - a third answer, never "not yet" |
| cost per promoted source when nothing was promoted | a sentence, not an infinity |
| any cost total where one record left the field blank | `None`, and `missing` says how many were short |

`SaturationRule` is `N` rounds under rate `X`, both configuration, both
required. There is no saturation score: one number would hide which of the three
metrics flattened and how many rounds it took, and those are the two things a
research lead acts on.

### The screening queue

A researcher scores a candidate on five named signals - relevance, novelty
potential, format-family potential, channel fit, evidence completeness - each
with a reason, each as a `DimensionScore`. The queue sorts what they supplied
and invents nothing; it reads no public metric at all, the same refusal
`score_opportunity` makes.

Ordering is `(status, -mean, candidate_id)`. The mean rather than the total,
because a total rewards whoever filled in more boxes; and a partially scored
candidate never sorts above a fully scored one, whatever its mean. An unscored
candidate keeps its place at the bottom rather than being dropped, because
`ScreeningCoverage` over the whole batch is the number that says whether the
ordering means anything yet.

**An assessment is not a decision.** `ScreeningRecommendation` is what a
reviewer thinks; `screen_candidate` is what the queue does, and it still takes
its own person, date and reason.

### Cost

`ResearchResourceRecord` charges spend to a batch and a `CostTier`. Manual
minutes, reasoning units, tool calls and search calls are each optional and each
stay missing when absent - `ai_platform/usage.py` makes the same call for the
same reason, and a system whose only budget needs provider telemetry stops
budgeting the day the provider changes. Reasoning units without a `UsageUnit`
are refused, and two quantisations in one batch do not add up.

`BatchReport` is the whole thing as twenty numbers and one list of absences.
`missing_measurements` is deliberately the longest section on a young batch.

## The flow

```
discovery -> evidence capture -> reference analysis -> opportunity dossier
          -> prioritization -> handoff to creative/R&D
```

as stages on the source record:

```
DISCOVERED -> SCREENED -> REFERENCE_ANALYZED -> OPPORTUNITY_CREATED
           -> REVIEWED -> PROTOTYPE_RECOMMENDED / REJECTED
```

Three of those are gated on an artefact existing, which is what makes it a
workflow rather than a label:

| Entering | Requires |
|---|---|
| `REFERENCE_ANALYZED` | at least one linked `ReferenceCase` |
| `OPPORTUNITY_CREATED` | at least one linked `OpportunityDossier` |
| `PROTOTYPE_RECOMMENDED` | a linked dossier, and a named reviewer |

`REJECTED` is terminal. Reopening a thread is a new source that cites the old
one, not a status flipped back.

```python
from intelligence.research import advance_source, link_reference_case, ResearchStage

source = advance_source(source, ResearchStage.SCREENED, on=today,
                        by="research_opportunity_lead", reason="Adjacent to our format.")
source = link_reference_case(source, "rc-elimination-marble-run")
source = advance_source(source, ResearchStage.REFERENCE_ANALYZED, on=today,
                        by="research_opportunity_lead", reason="Case file written.")
```

`store.thread(source_id)` assembles the whole package — source, cases,
dossiers, scorecards — which is what the creative team receives.

## Four refusals worth knowing before you write a record

**A number is a `Measurement`.** No research record has a bare float describing
the outside world. A `Measurement` carries a value, a unit, the method and a
mandatory `Evidence` pointer, so a researcher who has not measured something
cannot type a plausible number for it. This is the brief's one hard
prohibition, enforced by the type rather than by review.

**Research is never permanent.** `ResearchConfidence` refuses
`Freshness.PERMANENT`. Research observes a moving world; the route to an
invariant is the knowledge store — record a `Hypothesis`, test it, `promote()`
it on evidence of our own. Every finding must also name `would_change_if`, so
a trend observation cannot quietly become scripture.

**A local copy needs someone who authorised it.** The two copy statuses require
both a `local_copy_ref` and a `rights_basis`; the two non-copy statuses refuse
a `local_copy_ref` outright. There is no status meaning "we have the bytes and
nobody said we could", so a downloader would have nowhere to write. The system
works perfectly on a URL and a handful of public numbers.

**Missing data stays missing.** `derive()` computes only the ratios its inputs
support and *names* every one it could not, with the input that was absent. No
`views_per_day` without a publication date, no engagement ratio on zero views,
and no retention ever.

## What we cannot know about somebody else's video

`NEVER_KNOWABLE` — retention curve, average percentage viewed, average view
duration, click-through rate, monetization, traffic sources, and the causal
reason a video performed. It is exposed as `private_analytics_unavailable` on
every source and copied into every `DerivedMetrics`, so the limitation travels
with the data instead of living in a README nobody re-reads. Public metrics are
observations of a public surface; they are not analytics.

## A video idea is not a format opportunity

`FormatClass` has three values and two of them require a `FormatFamily`:

| Class | Family |
|---|---|
| `SINGLE_VIDEO` | refused — a reusable loop means it was not a single video |
| `FORMAT_EXTENSION` | required |
| `NEW_FORMAT_FAMILY` | required |

A `FormatFamily` states the reusable core loop, the dimensions that vary
between episodes, the variation space, the systems that get reused and the
audience question that survives from one episode to the next. "Marble race but
in a volcano" fills none of them in, which is the useful outcome.

## Superiority targets may say "I do not know"

| Status | Reference number | Also requires |
|---|---|---|
| `MEASURED` | required (a `Measurement`) | |
| `QUALITATIVE` | refused | `intent` |
| `UNKNOWN_PENDING_MEASUREMENT` | refused | `measurement_plan` |

The third status is what makes the other two trustworthy. Without it every
unmeasured dimension gets either dropped or given a plausible number, and a
month later the plausible number is indistinguishable from a real one.

## Scoring: the software adds up, it does not decide

A researcher supplies a score and a reason per dimension; `score_opportunity`
multiplies by weights nobody hid and sorts the same way twice. It takes a
rubric and a scorecard and **nothing else** — "higher views is a better
opportunity" is not a rule someone forgot to write, it is a rule with no input
to be written from.

Every `ScoreResult` carries the qualifications in the same frozen object, into
the same JSON file:

```
weighted_total      the number
weight_covered      the fraction of rubric weight actually scored
missing_dimensions  what was left blank
is_comparable       False whenever coverage is below 1.0
caveat              never empty; says what the total is not
```

There is no `confidence` field on a `ScoreResult`. Confidence is a property of
the evidence behind a dossier; a weighted mean of nine opinions is not evidence
about anything. Ties break on `(-total, opportunity_id)`, and ranking across
two rubrics is refused rather than silently allowed.

The shipped rubric is `opportunity-v1`. Weights are a decision, not a
measurement — change them in a *new* rubric id so old scorecards keep meaning
what they meant.

## From the command line

```
python -m intelligence.research list
python -m intelligence.research list --kind opportunity
python -m intelligence.research show opportunity op-elimination-race
python -m intelligence.research thread yt-competitor-marble-run
python -m intelligence.research rank --rubric opportunity-v1
python -m intelligence.research check --today 2026-09-16

python -m intelligence.research ingest captured.json --by research_lead
python -m intelligence.research candidates --state queued
python -m intelligence.research screen <id> --to screened_in --by X --reason "..."
python -m intelligence.research promote <id> --spec promotion.json
python -m intelligence.research funnel

python -m intelligence.research batch show rb-marble-race-2026q3
python -m intelligence.research batch report rb-marble-race-2026q3 --today 2026-09-17
python -m intelligence.research batch queue rb-marble-race-2026q3
```

`docs/research_ingestion_example/` holds a worked `captured.json` and
`promotion.json`; `docs/research_batch_example/` holds the batch plan those
candidates are collected under. `batch report` exits non-zero when a declared
stop condition has fired or a ceiling is over, so it can become a review gate
later without changing shape. `promote` has no flags for confidence or rights: a
`ResearchConfidence` is a level, a basis and what would overturn it, and a
command line that let a researcher skip those would manufacture them.

`check` runs the integrity and staleness sweeps and exits non-zero when either
finds something, so it can become a pre-merge step later without changing
shape. `rank` always prints the caveat under the table.

## Integrity

`store.integrity()` reports what a record cannot notice about itself: dangling
links in both directions, a reference case whose source is gone, a scorecard
against a rubric that does not define its dimensions, a candidate whose
discovery query is gone, and - the one worth having - two candidates holding one
video, which is the deduplication failing and is invisible from inside either
record. It does not look for
contradictions between two English sentences — that is a reasoning task, and
`KnowledgeStore.contradictions` draws the same line for the same reason.

## Deliberately not built yet

YouTube scraper, downloader, API client, browser automation, trend scheduler,
autonomous researcher, LLM content analyst, embeddings, vector DB, publishing
integration. Those come after these contracts prove stable.

What changed in this phase is only that there is now a **shape** for them to
produce. `IngestionEnvelope` is the boundary a connector sits outside of; the
connector is still nobody's code. `CaptureMethod.PLATFORM_API` exists as a
value because a researcher may legitimately export rows from an API console by
hand, and the evidence pointer is what makes that claim checkable - no request
is made anywhere in this package.

Nothing here imports production, nothing in production imports this, and the
package depends on `ai_platform`, `knowledge.company_os` and the standard
library only. URL parsing is hand-written rather than `urllib.parse`, because
the package forbids the `urllib` root outright and a scheme/host/path split is
twenty lines.
