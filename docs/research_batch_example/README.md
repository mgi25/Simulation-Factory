# Running one search without buying four hundred afternoons

`docs/research_ingestion_example/` puts one video into the system. This is what
you do when there are two hundred of them: decide what the search may cost
*before* you run it, record what each round actually produced, and let the
numbers say when another query would be buying re-reads.

Three files and six commands. Nothing here opens a URL either.

## 1. Write the budget and the stop conditions down first

`batch.json` is the plan. Two things in it are load-bearing and both are
refused if you leave them out:

- **`budget`** — at least one ceiling. "As many as it takes" is the sentence
  this record exists to stop somebody writing down.
- **`stop_conditions`** — at least one, and they are written *now*. A stop rule
  chosen after the numbers are visible is not a rule; it is a description of
  where somebody happened to stop, and it cannot fail.

```bash
python - <<'PY'
import json
from intelligence.research import ResearchBatch, ResearchStore
ResearchStore().add(ResearchBatch.from_dict(
    json.load(open("docs/research_batch_example/batch.json", encoding="utf-8"))))
PY

python -m intelligence.research batch show rb-marble-race-2026q3
```

The example declares three conditions: sixty unique candidates (stop), three
consecutive rounds contributing under 20% new candidates (review), and a
deadline (stop). `N` and `X` in the saturation rule are configuration — pick
them with the same care as the budget, because a rule nobody believes gets
escalated past on the first round.

## 2. Start collecting, on purpose

```bash
python - <<'PY'
import datetime as dt
from intelligence.research import BatchStatus, ResearchStore
ResearchStore().advance_batch(
    "rb-marble-race-2026q3", BatchStatus.COLLECTING,
    on=dt.date.today(), by="your_name",
    reason="Budget and stop conditions agreed.",
)
PY
```

A round recorded against a `planned` batch is refused. Starting to spend is a
decision, and it belongs in the history with a person against it.

## 3. Ingest, then record what the round showed you

Ingestion is unchanged — see the other example. What is new is that the *round*
is recorded too, including the results you had already seen:

```bash
python -m intelligence.research ingest \
    docs/research_ingestion_example/captured.json --by your_name

python - <<'PY'
import datetime as dt
from intelligence.research import DiscoveryRound, ResearchStore
store = ResearchStore()
observed = tuple(sorted(c.id for c in store.candidates()))
store.record_round(
    "rb-marble-race-2026q3",
    DiscoveryRound(query_id="dq-marble-race-2026q3", ran_on=dt.date.today(),
                   observed=observed),
    by="your_name",
)
PY
```

Record the whole result list, duplicates included. A round whose twenty results
are twenty candidates you already hold cost the same as one that found twenty
new ones, and the observation log is the only thing that can tell them apart —
the duplicate rate, the unique contribution per query and every saturation rate
are replays of it.

A round that would take the batch past a ceiling is refused **whole**, with the
limit named. It is not trimmed to fit: half an observation log is a research
record that has quietly lost evidence.

## 4. Screen, with the signals written down

`assessment.json` is one screener's five signals, each with a reason, plus the
evidence and the date. Replace `candidate_id` with an id `ingest` printed.

```bash
python - <<'PY'
import json
from intelligence.research import ResearchStore, ScreeningAssessment
ResearchStore().add(ScreeningAssessment.from_dict(
    json.load(open("docs/research_batch_example/assessment.json", encoding="utf-8"))))
PY

python -m intelligence.research batch queue rb-marble-race-2026q3
```

The queue sorts what you supplied and invents nothing. Fully scored candidates
come first, then partially scored, then the ones nobody has looked at — which
stay in the list, because how much of the batch is unscreened is the number
that says whether the ordering means anything yet.

An assessment is a recommendation, not a decision. Moving the candidate is
still `python -m intelligence.research screen <id> --to screened_in ...`, with
its own person, date and reason.

## 5. Record what it cost

`resource.json` charges an afternoon to the batch and to one funnel tier.
Everything in it is optional except measuring *something*; leave what you did
not measure as `null` rather than writing a zero.

```bash
python - <<'PY'
import json
from intelligence.research import ResearchResourceRecord, ResearchStore
ResearchStore().add(ResearchResourceRecord.from_dict(
    json.load(open("docs/research_batch_example/resource.json", encoding="utf-8"))))
PY
```

There is no `reasoning_units` in the example, because a person with a browser
did the work. That is not a gap in the accounting — the report will say
`reasoning_units: 1 of 1 resource record(s) did not measure it`, and every
minutes-based ratio still works.

## 6. Read the report

```bash
python -m intelligence.research batch report rb-marble-race-2026q3
```

Twenty numbers and a list of everything nobody measured. It exits non-zero when
a declared stop condition has fired or a ceiling has been spent past, so it can
become a review gate later without changing shape.

Read `missing measurements` first. On a young batch it is the longest section,
and it should be — a report where it is empty after one round has guessed at
something.

## When a condition fires

```
batch rb-marble-race-2026q3 ... 
  stop conditions
    FIRED max_unique_candidates    [stop] 60 of 60 unique_candidates
```

Two legitimate next moves, and neither of them is "keep going":

```bash
# the usual one: stop collecting and screen what you have
python - <<'PY'
import datetime as dt
from intelligence.research import BatchStatus, ResearchStore
ResearchStore().advance_batch("rb-marble-race-2026q3", BatchStatus.SCREENING,
                              on=dt.date.today(), by="your_name",
                              reason="Ceiling reached; screening what we found.")
PY

# the other one: somebody with authority says the ceiling was wrong
python - <<'PY'
import datetime as dt
from intelligence.research import BatchBudget, ResearchStore
ResearchStore().escalate_batch(
    "rb-marble-race-2026q3", on=dt.date.today(), by="your_name",
    reason="The niche is wider than the first query showed.",
    authorised_by="ceo",
    budget=BatchBudget(max_unique_candidates=90, max_candidate_observations=180,
                       max_promoted_candidates=6, max_reference_cases=4,
                       max_human_review_minutes=360, deadline=None),
)
PY
```

The escalation stays in the history with the authoriser's name in it, forever.
That is the whole mechanism: continuing is allowed, and it is never free.
