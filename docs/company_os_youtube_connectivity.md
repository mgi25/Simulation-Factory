# Company OS — YouTube connectivity

YouTube is the one place this company's evidence genuinely lives behind an
authenticated network call, and Company OS is the one part of this repository
that is not allowed to make one. The first version of this connector resolved
that tension the wrong way round: it put OAuth, `urllib` and a loopback HTTP
server inside `company/youtube/`, and then widened the integration gate until
the result passed. This version resolves it the other way. The network half
moved out to `tools/youtube_fetch`, a production root where a socket is
ordinary, and Company OS was handed back the thing it is good at — refusing to
believe a number that cannot say where it came from.

```text
Google OAuth 2.0 · YouTube Data API v3 · YouTube Analytics API v2
        |
        |  tools/youtube_fetch   (production root; network allowed;
        |                         imports nothing from company/, ai_platform/,
        v                         knowledge/ or intelligence/)
sanitized artifact JSON on disk
        |
        |  company/youtube       (Company OS; network-free; reads a file)
        v
validated evidence -> ApiArtifactSource + MetricObservation -> AnalyticsStore
```

The two halves never import each other. The only thing that crosses the
boundary is a file, and the file is the contract.

## The boundary, and why the gate did not move

`company/integration/policy.py` and `company/integration/checks.py` are
**unmodified** by this work. `POLICY_VERSION` is still 1. The required check is
still `health.no_network_or_model_dependency`, and it still forbids every one of
the network and model import roots across all four Company OS roots — `company`,
`ai_platform`, `knowledge`, `intelligence` — with no allow-list, no path
exclusion and no advisory downgrade. `production.no_publishing_capability`
likewise still forbids every network import and every process spawn anywhere
under those roots.

That includes `urllib`. `from urllib.parse import urlparse` is a network import
as far as the gate is concerned, and it is not permitted anywhere under
`company/`, even for taking a string apart. If a future change needs to parse a
URL inside Company OS, it splits the string by hand, or the work belongs on the
other side of the boundary.

The check that keeps the fetcher honest in the other direction is
`architecture.production_does_not_import_company_os`. `tools/` is a production
root, so `tools/youtube_fetch` may open a socket but may not import
`company.*`, `ai_platform.*`, `knowledge.*` or `intelligence.*`. It is standard
library only. Neither side can quietly grow into the other without a required
gate check failing.

Two rules follow, worth stating plainly because they are what makes the
architecture reviewable rather than merely tidy:

- **Company OS performs no network access and holds no credential.** There is no
  token store, no refresh grant, no client secret and no callback server under
  `company/`. The ingester's entire input is a path to a JSON file.
- **A failing gate check is evidence, not paperwork.** If a commit needs the gate
  relaxed in order to pass, that is the commit telling you the design is wrong.
  The first version of this connector failed in exactly that way.

## OAuth scopes — exactly two

The fetcher requests, and only ever requests:

```text
https://www.googleapis.com/auth/youtube.readonly
https://www.googleapis.com/auth/yt-analytics.readonly
```

`REQUIRED_SCOPES` in `tools/youtube_fetch/config.py` is both the requested set
and the required set, and a test fails if that tuple grows. No write scope
exists. After the authorization-code exchange the fetcher compares the scopes
Google actually granted against `REQUIRED_SCOPES` and raises `MissingScopeError`
**before** anything reaches the token store, so a partial consent leaves behind
no stored grant to be confused about later.

`yt-analytics-monetary.readonly` is gone — not optional, not behind a flag, but
removed, along with `--include-monetary-scope` and the `include_monetary`
parameter. Revenue is `company/finance`'s subject, and finance's whole design is
that money enters as an explicit, evidenced record rather than as a number a
connector happened to be able to read. A monetary scope here would have created
a second, quieter path to the same figures, and the two would eventually
disagree. If revenue is ever wanted, it arrives through finance, under finance's
rules.

## The sanitized artifact

The fetcher writes one canonical JSON file (UTF-8, sorted keys). Everything
Company OS ingests comes from it, and from nothing else.

```jsonc
{
  "artifact_version": 1,
  "producer": "tools.youtube_fetch",
  "producer_version": "1.0",
  "fetched_at": "2026-09-17T10:00:00+00:00",
  "granted_scopes": [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly"
  ],
  "channel": {
    "channel_id": "UC-company",
    "channel_title": "Simulation Factory",
    "subscriber_count": 1234,
    "subscriber_count_unavailable_reason": "",
    "video_count": 7,
    "view_count": 45678,
    "uploads_playlist_id": "UU-company",
    "source": "youtube_data_api_v3.channels.list"
  },
  "videos": [
    {
      "video_id": "abcDEF_1",
      "channel_id": "UC-company",
      "title": "Test 1",
      "published_at": "2026-09-10T08:00:00+00:00",
      "duration": "PT1M2S",
      "duration_seconds": 62,
      "privacy_status": "public",
      "upload_status": "processed",
      "source": "youtube_data_api_v3.videos.list"
    }
  ],
  "video_retrieval": {
    "requested": 10,
    "returned": 10,
    "complete": true,
    "pages_followed": 2,
    "missing_video_ids": [],
    "notes": []
  },
  "analytics": [
    {
      "channel_id": "UC-company",
      "video_id": "abcDEF_1",
      "start_date": "2026-09-01",
      "end_date": "2026-09-16",
      "temporal_semantics": "interval",
      "source": "youtube_analytics_api_v2.reports.query",
      "complete": true,
      "excludes": [],
      "metrics": [
        {"name": "views", "source_metric": "views", "unit": "views",
         "value": 100, "available": true, "unavailable_reason": ""},
        {"name": "comments", "source_metric": "comments", "unit": "comments",
         "value": null, "available": false,
         "unavailable_reason": "API returned no rows for the requested range"}
      ]
    }
  ],
  "api_calls": [
    {"method": "GET",
     "endpoint": "https://youtubeanalytics.googleapis.com/v2/reports",
     "status": 200, "response_bytes": 412, "latency_ms": 37,
     "succeeded": true, "error_kind": ""}
  ],
  "raw": {"channels.list": {}, "playlistItems.list": [], "videos.list": [], "reports.query": []}
}
```

The hard rules, all of which `company/youtube/artifact.py` re-validates on read
rather than trusting:

- `endpoint` is scheme, netloc and path with **the query string stripped**. A
  full URL would carry `access_token`, and this telemetry is written to disk.
- An access token, refresh token, client id, client secret, `Authorization`
  header, authorization code, PKCE verifier or `state` value is never present
  anywhere in the file. Redaction is not the mechanism; those values are simply
  never assembled into the artifact in the first place.
- `available == false` if and only if `value` is null and `unavailable_reason` is
  non-empty. **An unavailable metric is never zero.** Zero is a measurement;
  "the API returned no rows" is not, and that difference is the entire reason the
  field exists.
- `temporal_semantics` is `"interval"`. This version emits nothing else.
- `raw` is written only with `--include-raw`; when absent the key is omitted
  entirely rather than set to null.
- If any call fails, or a paginated walk cannot be completed, **no artifact file
  is written at all**. There is therefore no route by which a half-finished pull
  becomes a committed observation.

### Metric vocabulary

The fetcher normalizes provider metric names; the ingester maps them onto the
metric registry Studio ingestion already uses, so an API reading and a Studio
reading of the same quantity land on the same `MetricDefinition`.

| artifact `name` | provider metric | unit | registry metric | transform |
|---|---|---|---|---|
| `views` | `views` | views | `views` | identity |
| `estimated_minutes_watched` | `estimatedMinutesWatched` | minutes | `watch_time_hours` | `/ 60.0` |
| `average_view_duration_seconds` | `averageViewDuration` | seconds | `average_view_duration_seconds` | identity |
| `average_view_percentage` | `averageViewPercentage` | fraction | `average_percentage_viewed` | `* 0.01`, in the fetcher; **may exceed 1.0** |
| `subscribers_gained` | `subscribersGained` | subscribers | `subscribers_gained` | identity |
| `subscribers_lost` | `subscribersLost` | subscribers | `subscribers_lost` | identity |
| `likes` | `likes` | likes | `likes` | identity |
| `comments` | `comments` | comments | `comments` | identity |
| `shares` | `shares` | shares | `shares` | identity |

No monetary metric exists in either half.

#### `average_percentage_viewed` has no ceiling, and that is a correction

The first live pull of the Physics Loop channel returned
`averageViewPercentage = 118.41` for a Short. The fetcher normalized it to
`1.1841`, correctly, and the metric registry described itself as

> fraction of video length, 0.0-1.0

which made the one interesting reading in the pull the one the contract called
impossible. Nothing clamped it — the clamp had never been written — so the
defect was latent rather than harmless: the next person to reconcile the two
had a sentence in the registry telling them to clamp, and clamping would have
turned "this Short is watched more than once per view" into "this Short is
watched exactly once through".

A percentage viewed is watch duration over video length. Its denominator is not
a population, so the numerator can lap it: a viewer who lets a Short loop keeps
accumulating watch time past the end. **Values above 1.0 are valid.** The
corrected contract is

> average fraction of video viewed; 1.0 = 100%; values above 1.0 are valid when
> repeat viewing or looping makes the average watch duration exceed the video's
> duration

and it is now enforced rather than described. `MetricDefinition` carries
`unbounded_above`, derives `minimum`/`maximum` from it, and `MetricObservation`
checks the value at construction:

| metric | floor | ceiling | why |
|---|---|---|---|
| `average_percentage_viewed` | 0.0 | none | a view can lap the video |
| `retention_at_3s`, `retention_at_50pct`, `click_through_rate`, `traffic_source_share` | 0.0 | 1.0 | a share of a population cannot exceed the population |
| `views`, `likes`, durations, … | 0.0 | none | a count has no full scale |
| `estimated_revenue` | none | none | a refund is a real negative amount |

Restoring the old assumption now means flipping a declared field, and
`tests/test_company_youtube_live_findings.py` fails when somebody does.

### Channel-level evidence is not a `MetricObservation`

A pull asks `reports.query` for the channel as well as for each video, so a real
artifact carries one row set with no `video_id`. It is a genuine measurement —
"the channel averaged 71.94% viewed this week" is something the company wants —
and it is **not** an observation, because an observation is recorded against a
deliverable and the channel is not one.

The tempting fix is the failure. A `deliverable_id` of `"channel"` would put a
total into the same population as the videos it totals, and every later average,
baseline and experiment over deliverables would count that week twice. So the
two levels are separated instead of one being discarded:

```
artifact
├── channel evidence
│   └── the channel-wide row set  →  retained in the artifact, in the evidence
│                                    envelope, and named in
│                                    ApiIngestionResult.channel_reports
└── video evidence
    └── the per-video row sets    →  MetricObservation, once a mapping says
                                     which deliverable the video is
```

`ApiIngestionResult.to_dict()` reports both under `evidence_levels`
(`{"channel": n, "deliverable": m}`) and lists the channel row sets under
`channel_evidence`, so a consumer can tell them apart without knowing this
module's field names. The diagnostic is an `AGGREGATE_ROW` **note** — the same
kind and severity the Studio importer gives a `Total` row, which is the same
thing seen through the other door — rather than the error it used to be. An
expected, correct, every-pull outcome that sets an error flag only teaches an
operator to ignore the error flag.

The channel's actual numbers live in the artifact and in the envelope
`YouTubeEvidenceStore` appends; the result object prints no reading, by the same
rule `inspect` follows.

## Observation identity: what makes two numbers the same reading

The interesting question for an evidence ledger is not "where did this number
come from" but "when are two numbers the same reading". Get that wrong in one
direction and a nightly pull appends a duplicate row every night; get it wrong in
the other and a corrected figure silently overwrites the one a decision was made
on.

So an observation id is derived from what was measured, and from nothing else:

```python
identity = {
    "api": "youtube_analytics_api_v2.reports.query",
    "channel_id": report.channel_id,
    "video_id": report.video_id,
    "deliverable_id": deliverable.deliverable_id,
    "metric": metric_name,          # the registry name, e.g. "watch_time_hours"
    "start_date": report.start_date.isoformat(),
    "end_date": report.end_date.isoformat(),
    "measurement": "interval",
}
observation_id = f"ya-{fingerprint(identity)}"
```

Deliberately **excluded**: the artifact path, the sequential evidence filename,
the evidence record ref, `fetched_at`, the artifact digest — and the value
itself. Every one of those changes between two pulls of the same window, and if
any of them entered the identity, replay would stop being a no-op and the ledger
would fill with duplicates each claiming to be a different reading.

`observed_at` is derived the same way, from the window rather than from the
fetch: midnight UTC on the day after `end_date`, the instant the interval closes.
That is the same reasoning as `studio_ingest._coverage`. Provenance evidence is
content-addressed for the same reason —
`Evidence(kind="external", ref=f"youtube-api:{source.short_digest}", ...)` — so
two ingestions of one artifact produce byte-identical records.

### Replay and conflict

Commit semantics mirror `studio_ingest.commit_ingestion` exactly:

| situation | outcome |
|---|---|
| id absent from the store | written |
| id present, `prior.to_dict() == new.to_dict()` | `already_present`; nothing written |
| id present, content differs | conflict |

The third row is the revised-value case, and it is the one that matters. YouTube
Analytics revises figures after the fact: views for a closed window can read 100
on Monday and 118 on Wednesday. Both are honest readings of the same identity,
and the store cannot decide which one a person should act on. So with the default
`allow_conflicts=False` the commit raises `LedgerViolation` and writes **nothing
at all** — not the observations, and not even the `ApiArtifactSource` record. A
partially applied ingestion is worse than a refused one, because it looks
finished. The ingester also runs the `snapshot_key` disagreement scan that Studio
ingestion runs.

### Interval readings cannot collide with cumulative ones

Every observation this package commits carries
`breakdown = {"measurement": "interval"}`. A Studio or Data API cumulative
reading carries no breakdown at all, so `MetricObservation.key` differs and the
two can never be mistaken for each other — not by the store, not by a comparison,
not by the dashboard. "Views in the last 28 days" and "views since publication"
are different quantities wearing the same name, and this is the structural guard
against ever averaging them together.

### The evidence envelope digest

`company/youtube/store.py` fingerprints the envelope **once**, over one declared
basis:

```python
CANONICAL_FIELDS = ("schema_version", "kind", "source", "artifact_digest",
                    "date_range", "identity", "normalized", "raw",
                    "api_calls", "ingested_from")
```

`evidence_id` is `f"youtube-{digest}"`, and the pointer's fingerprint is that
same digest, computed once. The earlier version fingerprinted, inserted the id,
then fingerprinted again, which produced two digests for one record and no way
for a reader to know which one to check against. Credentials and authenticated
headers are excluded from the basis by construction: they are never in the
artifact, so they are never in the envelope.

## Completeness: an absence is a fact about the data

Nothing here may report a short list as a complete one.

On the fetch side, `playlistItems.list` is followed through `nextPageToken` until
the requested number of ids is collected or the playlist is exhausted, and
`videos.list` is called in chunks of at most 50 ids. Any playlist id that
`videos.list` does not return is recorded in `video_retrieval.missing_video_ids`
— **the exact ids, not a count** — so the gap can be investigated rather than
merely noticed. Analytics rows that do not come back stay `available: false` with
a reason attached.

On the ingest side, that incompleteness is mapped onto the type that already
exists for it:

```python
DataScope(
    population=...,
    complete=False,
    excludes=("videos.list did not return 2 of 10 requested videos: abcDEF_1, abcDEF_2",),
    limitations=("YouTube Analytics data can be delayed or revised after retrieval.",),
)
```

`DataScope.__post_init__` already refuses `complete=False` with an empty
`excludes`, so an incomplete pull cannot be recorded without saying what is
missing. That refusal is relied upon rather than re-implemented here.

## Operating it

The authenticated half, outside Company OS:

```powershell
python -m tools.youtube_fetch auth
python -m tools.youtube_fetch status
python -m tools.youtube_fetch fetch --days 28 --videos 10 --video-analytics --out artifact.json
python -m tools.youtube_fetch smoke-test
```

Client credentials are supplied locally and never in Git, through
`YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET` and `YOUTUBE_REDIRECT_URI`, or
through `YOUTUBE_CLIENT_CONFIG_FILE` pointing at an ignored Google OAuth client
JSON file; environment variables win. The refresh grant is protected with
current-user DPAPI on Windows and with a mode-0600 file inside a mode-0700
directory elsewhere. Secrets are declared `field(repr=False)`, and every error
surface — a DPAPI `OSError`, a token-endpoint error, an HTTP error, the CLI's
top-level handler — passes through `SecretRedactor` before anything is printed.

The Company OS half, which touches no network and needs no credential:

```powershell
python -m company.youtube inspect artifact.json
python -m company.youtube assignments artifact.json --out assignments.json
python -m company.youtube ingest artifact.json --assignments assignments.json
python -m company.youtube ingest artifact.json --assignments assignments.json --state-dir C:\path\to\company-state --commit --keep-evidence
```

### Mapping videos to deliverables

`assignments.json` is the operator's declaration of what each video *is*, which
is the one thing the platform cannot tell us. The schema is a JSON object keyed
by YouTube video id:

```json
{
  "VIDEO_ID": {
    "deliverable_id": "race-001",
    "kind": "short",
    "format_id": "marble_race",
    "version": ""
  }
}
```

| field | required | rule |
|---|---|---|
| *key* | yes | the YouTube video id, case-sensitive, exactly as the platform spells it |
| `deliverable_id` | yes | lowercase `[a-z0-9._-]`, starting alphanumeric — so it is **never** the video id |
| `kind` | yes | one of `video`, `short`, `prototype`, `experiment_render`, `format_version` |
| `format_id` | yes | the format family tag, e.g. `marble_race` |
| `version` | no | the iteration within that format |

`docs/youtube_assignments_template.json` holds that example with placeholder
keys, and `tests/test_company_youtube_live_findings.py` loads it through the
real `load_assignments`, so the documented shape cannot drift from the shape the
code accepts.

`kind` and `format_id` are supplied, never inferred from a duration or a title:
a family guessed off a title would carry the authority of a record and silently
mis-group every comparison downstream. A video with no entry is reported as
unassigned and produces no observation.

The operator workflow, which invents nothing:

```powershell
# 1. what needs classifying, and a template keyed by the real video ids
python -m company.youtube assignments artifact.json --out assignments.json

# 2. a person edits assignments.json, replacing every REPLACE_WITH_... value
#    with what that video actually is

# 3. dry run: read it back and see exactly what would be recorded
python -m company.youtube ingest artifact.json --assignments assignments.json

# 4. commit
python -m company.youtube ingest artifact.json --assignments assignments.json --state-dir C:\path\to\company-state --commit --keep-evidence
```

Step 1 prints each unassigned video's id, publication instant, duration and
title — enough for a person to recognise it — and writes a file in exactly the
schema above with every value set to `REPLACE_WITH_…`. The title is printed to
help a human decide and is never read back as a classification. The command
exits 1 while anything is unassigned, so a scripted run cannot read "nothing
committed" as "done".

`load_assignments` **refuses** any field still holding a `REPLACE_WITH_`
placeholder, including a half-filled file whose `kind` is valid but whose
`deliverable_id` is not. Without that refusal the template would be the most
dangerous file in the system: `REPLACE_WITH_DELIVERABLE_ID` is a perfectly legal
tag, so validation alone would accept it and attach a week of real readings to a
deliverable nobody ever made.

`inspect` writes nothing. `ingest` is a **dry run by default** — it parses,
validates and reports everything it would record, and needs `--commit` before it
appends anything. `--keep-evidence` additionally appends the whole artifact to
the evidence envelope store under `--state-dir`.

## Review checklist

An engineer reviewing a change to either half should be able to answer yes to all
of these:

1. Do `company/`, `ai_platform/`, `knowledge/` and `intelligence/` still import
   no network root, `urllib` included?
2. Does `tools/youtube_fetch` still import nothing from those four roots?
3. Is `REQUIRED_SCOPES` still exactly the two read-only scopes, and does a test
   still fail if that tuple grows?
4. Does every committed observation still carry
   `breakdown={"measurement": "interval"}`?
5. Is everything fetch-dependent — a timestamp, a path, a filename, a digest —
   still absent from the observation identity?
6. Does a failed or incomplete fetch still write no artifact, and does a
   conflicting commit still write nothing at all?
7. Does `average_percentage_viewed` still declare `unbounded_above`, and is
   there still no clamp anywhere between the API response and the store?
8. Is a channel-wide row set still retained as evidence, still reported as a
   note rather than an error, and still absent from every `MetricObservation`
   under any deliverable id?
9. Does an unedited or half-filled assignments template still fail to load?

Any "no" is a design change rather than a fix, and belongs in the gate report
before it belongs in this file.
