# Company OS analytics and experiments

What happened after we published, what we changed, and what the evidence
actually supports. Deterministic, append-only, standard library only.

Read `__init__.py` first — it carries the five rules the package is built on.
This file is the map and the worked example.

## The loop

```
published deliverable
  -> dated observations        immutable, sourced, never overwritten
  -> experiment comparison     what changed, what was held, at what age
  -> qualified result          a verdict about our prediction, not about the world
  -> postmortem                including when it went badly
  -> durable learning          or the sharper hypothesis it produced instead
```

Analytics **records observations**. Experiments **define comparisons**. Learning
**interprets evidence cautiously**. Those are three record types on purpose: a
system that merges them produces "the cold open worked" from one video that did
well in a week when the platform happened to be promoting Shorts.

## Modules

| module | what it owns |
| --- | --- |
| `common.py` | validators, `Provenance`, `DataScope`, the UTC instant rule |
| `windows.py` | `AgeWindow` (hours since publication) and `DateRange` (calendar) |
| `metrics.py` | `MetricDefinition`, the registry, the private-metric line |
| `deliverable.py` | `AnalyzedDeliverable` — the analytics handle, not a renderer model |
| `genome.py` | `ContentFeatures` — recorded feature tags, never inferred |
| `observations.py` | `MetricObservation`, `observe()`, `ObservationSeries` |
| `references.py` | pointers into finance, research, runtime; the competitor boundary |
| `experiments.py` | `ExperimentSpecification`, `Expectation`, `KillCondition` |
| `comparison.py` | `compare_deliverables` — and the three ways a pair fails to compare |
| `results.py` | `Verdict`, `CausalAssessment`, `evaluate_experiment` |
| `baseline.py` | `FormatBaseline`, `MetricSummary`, `OutlierRule` |
| `formats.py` | grouped descriptive analytics; association, never ranking |
| `postmortem.py` | `DeliverablePostmortem` — no failed video without learning |
| `learning.py` | `AnalyticsHypothesis`, `AnalyticsLearning`, `promote()` |
| `report.py` | `AnalyticsReport` — the seven questions, capped, deterministic |
| `store.py` | append-only JSON under a caller-supplied `state_dir` |
| `integrity.py` | the cross-record checks no single record can run on itself |

## The causality guard

The one thing this phase exists to get right.

`Verdict` answers **did the metric move the way we guessed?** — arithmetic over
expectations recorded beforehand.

`CausalAssessment` answers **did our change cause it?** — and almost always says
no. `causal_claim_supported` is a *property*, derived from four conditions:

1. assignment was controlled (`RANDOMIZED_SPLIT` only);
2. exactly one variable changed;
3. the sample reached the minimum the specification set beforehand;
4. every primary metric actually compared.

There is no field to set, no `force=` parameter, and no path from an
observational comparison to a causal claim. When any condition fails, `blockers`
names which, and `statement` returns the association wording. Even when all four
pass, the wording stays qualified — a randomised split tells you about that
split, that audience, that week.

An experiment can support its hypothesis **and** support no causal claim. That
is the normal case for everything we publish, and `AnalyticsReport` lists it
under "not concluded" so the distinction reaches the person deciding what to
make next.

## Worked example

```python
import datetime as dt
from knowledge.company_os.records import Evidence
from company.analytics import (
    AnalyzedDeliverable, ComparisonBasis, ContentFeatures, DataScope, DataSource,
    DeliverableKind, Direction, Expectation, ExperimentSpecification,
    FeatureDimension, FIRST_24H, KillCondition, Provenance, Variable,
    compare_deliverables, evaluate_experiment, observe,
)

UTC = dt.timezone.utc
evidence = (Evidence(kind="document", ref="docs/exports/studio_2026_09_10.csv"),)
provenance = Provenance(
    source=DataSource.OWN_STUDIO_EXPORT,
    retrieved_by="studio csv export 2026-09-10",
    evidence=evidence,
)
scope = DataScope(population="all viewers of this deliverable")

variant = AnalyzedDeliverable(
    deliverable_id="race-short-014",
    kind=DeliverableKind.SHORT,
    format_id="race_short",
    version="v31",
    published_at=dt.datetime(2026, 9, 8, 12, 0, tzinfo=UTC),
    features=ContentFeatures.from_labels({FeatureDimension.HOOK_TYPE: "cold_open"}),
)

reading = observe(
    "obs-014-apv", variant, "average_percentage_viewed", 0.47,
    dt.datetime(2026, 9, 9, 8, 0, tzinfo=UTC), provenance, scope,
    denominator_value=42.0,
)
```

The specification says what changed, what was held, and what would stop the
experiment — all before the numbers exist:

```python
spec = ExperimentSpecification(
    experiment_id="exp-cold-open",
    objective="Find out whether a cold open holds more of the first day's audience.",
    hypothesis="A cold open raises average percentage viewed against the slow reveal.",
    basis=ComparisonBasis.MATCHED_PAIR,
    control_id="race-short-013",
    variant_ids=("race-short-014",),
    variables_changed=(
        Variable("hook_type", "Cold open replaces the slow reveal.", "slow_reveal", "cold_open"),
    ),
    variables_locked=(Variable("camera_style", "Chase rig unchanged from v30."),),
    primary_metrics=("average_percentage_viewed",),
    guardrail_metrics=("click_through_rate",),
    observation_window=FIRST_24H,
    minimum_sample=6,
    owner="MGI",
    created_on=dt.date(2026, 9, 5),
    expectations=(
        Expectation("average_percentage_viewed", Direction.UP, "The hook lab suggested the drop is in the first three seconds."),
    ),
    kill_conditions=(
        KillCondition("kc-ctr-floor", "click_through_rate", Direction.DOWN, 0.05,
                      "Below a 5% CTR the format stops being promoted at all."),
    ),
)
```

And the result is qualified whether we like it or not:

```
verdict:  supports_hypothesis
causal:   False
blocker:  assignment was not controlled: a matched_pair comparison observes two
          things that differ in the audience they reached, the week they reached
          it and what the platform was promoting, as well as in what we changed
```

## Boundaries

- **Finance owns money.** `FinanceReference` carries record ids and nothing to
  sum. `summarise_metric` refuses a monetary metric outright rather than
  producing a second revenue total that disagrees with finance's.
- **Research owns the outside world.** `ResearchReference` cites dossiers;
  `CompetitorPublicReference` carries public metric *names* and no values, and
  refuses a private one.
- **The runtime owns what work consumed.** `ExecutionReference` carries record
  ids, no token counts.

Analytics imports no other Company OS subsystem beyond
`company.runtime.state_paths` and `company.validation.errors`, so the capsule
edge `company-organizational-intelligence -> company-analytics-experiments`
cannot close a cycle.

## What is deliberately absent

No YouTube connector, no OAuth, no Studio scraper, no scheduler, no prediction
model, no embeddings, no LLM analysis, no autonomous experiment launcher
(constitution rule 17 — prove need before building).

No title NLP, in this phase or a later one. Feature tags are recorded by whoever
made the thing; a feature read off a title is a guess about how a video was made
wearing the authority of a record. The suite greps this package for any read of
`title` outside serialisation and the report's display line.

**No score.** Not for a video, a format, an experiment or the channel. The
company's objective — long-term profitable audience growth — is not one number,
and a single number here would be optimised in its place. The suite walks every
field of every record in the package for score-shaped names, so the absence
survives the next convenience helper.

## Command line

```
python -m company.analytics metrics [--verbose]   what each metric name means
python -m company.analytics windows               the standard observation windows
python -m company.analytics rules                 what is refused at construction
python -m company.analytics report <state_dir>    render the analytics report
python -m company.analytics check <state_dir>     cross-record integrity
```

Every subcommand reads. None records, concludes or publishes.

## Tests

`tests/test_company_analytics.py`.
