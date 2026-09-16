# Putting one real public video into Company OS

Three files and four commands. Nothing here opens a URL: you read the public
page, you write down what it showed, and the system checks that what you wrote
is the shape of a public observation rather than an inference.

The example uses an obviously fake video id so the files can be committed. Use
a real one.

## 1. Write the query down first

`query.json` is the search you are about to run, recorded so that running it
again next month is recognisably the same run. Load it with:

```bash
python - <<'PY'
import json, datetime as dt
from intelligence.research import DiscoveryQuery, ResearchStore
ResearchStore().add(DiscoveryQuery.from_dict(
    json.load(open("docs/research_ingestion_example/query.json", encoding="utf-8"))))
PY
```

## 2. Capture what the page showed

Open the video. Write what you can see into `captured.json`: title, channel,
publication date, duration, views, likes, comments. Leave out anything you
could not see - a field you omit stays unknown, and a field you guess at is
the one thing this system is built to refuse.

`evidence_ref` points at something a reader could check: a note in
`docs/validation/`, a dated screenshot path, a commit. It is required, because
an externally captured number with nothing behind it is an assertion.

You cannot write `audience_retention`, `average_percentage_viewed`, `rpm`,
`revenue`, `impressions`, `traffic_sources` or `subscriber_conversion`. No
public page shows those for somebody else's video, and the payload refuses them
by name rather than storing an inference that will later look like an
observation.

```bash
python -m intelligence.research ingest \
    docs/research_ingestion_example/captured.json --by your_name
```

The same video captured again - from a Short URL, from a different query, next
month - merges into the same candidate and adds its reading. It does not
create a second row and does not overwrite the first reading.

## 3. Screen it

```bash
python -m intelligence.research candidates
python -m intelligence.research screen <id> --to queued \
    --by your_name --reason "Adjacent to a format we already run."
python -m intelligence.research screen <id> --to screened_in \
    --by your_name --reason "The loop renews at every junction, without narration."
```

This is the last cheap place to say no. Screening out costs a sentence;
everything past here costs an afternoon.

## 4. Promote the ones worth an afternoon

```bash
python -m intelligence.research promote <id> \
    --spec docs/research_ingestion_example/promotion.json
```

`promotion.json` carries the two judgements a command line should not default
for you: the `ResearchConfidence` (a level, why, and what would overturn it)
and the `RightsStatus`. `link_only` is almost always correct - we hold a URL
and some public numbers, and that is enough for everything downstream.

A screened-out candidate cannot be promoted by any argument combination.

## Then check it

```bash
python -m intelligence.research check --today $(date +%F)
python -m intelligence.research thread <source id>
```
