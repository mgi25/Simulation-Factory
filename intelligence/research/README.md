# Company OS research & intelligence

Six record types, one seven-stage workflow, one directory of JSON files. No
database, no embeddings, no network. Everything here is `dataclasses` and
`json`, same as the knowledge store it sits beside.

This layer stores and evaluates research. It does not go and get it: there is
no scraper, no API client, no browser driver, no downloader and no model. That
is deliberate and it is the sequencing in `docs/company_os_v1_bootstrap.md` —
the contracts prove stable first, and automated discovery is built against a
schema that already works.

## Where records live

```
intelligence/research/records/
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

## The six types

| Type | Answers | Required beyond the common fields |
|---|---|---|
| `ResearchSource` | What did we find, and what may we keep of it? | `reference`, `rights`, `confidence` |
| `ReferenceCase` | What does it teach, and where is the line? | nine sections, all of them, incl. `originality` |
| `OpportunityDossier` | What could we make, and why do we believe it? | `evidence` (≥1), `limitations` (≥1), `format_class` |
| `VideoIntelligenceDossier` | What is this video testing? | `experiment`, `kill_conditions` (≥1), `superiority_targets` (≥1) |
| `ScoringRubric` | What are we weighing, and how heavily? | `dimensions` (≥1), explicit weights |
| `OpportunityScorecard` | What did a researcher judge, and why? | `scores` (≥1), each with a `reason` |

Common to most: `id`, `created`, an author, and a `ResearchConfidence`.

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
```

`check` runs the integrity and staleness sweeps and exits non-zero when either
finds something, so it can become a pre-merge step later without changing
shape. `rank` always prints the caveat under the table.

## Integrity

`store.integrity()` reports what a record cannot notice about itself: dangling
links in both directions, a reference case whose source is gone, a scorecard
against a rubric that does not define its dimensions. It does not look for
contradictions between two English sentences — that is a reasoning task, and
`KnowledgeStore.contradictions` draws the same line for the same reason.

## Deliberately not built yet

YouTube scraper, downloader, API client, browser automation, trend scheduler,
autonomous researcher, LLM content analyst, embeddings, vector DB, publishing
integration. Those come after these contracts prove stable. Nothing here
imports production, nothing in production imports this, and the package depends
on `ai_platform`, `knowledge.company_os` and the standard library only.
