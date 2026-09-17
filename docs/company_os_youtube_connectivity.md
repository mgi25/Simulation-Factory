# Company OS — read-only YouTube connectivity

This connector retrieves evidence from the authenticated company's own channel.
It uses the YouTube Data API v3 and YouTube Analytics API v2. It does not upload,
edit, delete, comment, or recommend.

## Security boundary

The default OAuth scopes are:

- `https://www.googleapis.com/auth/youtube.readonly`
- `https://www.googleapis.com/auth/yt-analytics.readonly`

The optional `yt-analytics-monetary.readonly` scope is requested only when the
operator passes `auth --include-monetary-scope`. Revenue is not retrieved by
the current connector. No YouTube write scope exists in the implementation.

Access tokens live only in process memory. The refresh grant is stored under
the current user's local configuration directory by default. On Windows it is
encrypted with current-user DPAPI; on other platforms it is stored under a
mode-0600 file in a mode-0700 directory. `YOUTUBE_TOKEN_FILE` can choose an
alternate ignored local path. API telemetry records endpoint paths without
queries, status, latency, response size, and failure type—never headers,
request bodies, authorization codes, or tokens.

## Google Cloud setup

1. Create or select a Google Cloud project.
2. Enable **YouTube Data API v3** and **YouTube Analytics API**.
3. Configure the OAuth consent screen. Add the Google account that owns the
   channel as a test user while the app remains in testing.
4. Create an OAuth 2.0 client suitable for a local/desktop application.
5. Use a loopback redirect such as
   `http://127.0.0.1:8765/oauth2callback`. The configured value must match.
6. Supply the client locally—never in Git—using environment variables:

   ```powershell
   $env:YOUTUBE_CLIENT_ID = '<your OAuth client id>'
   $env:YOUTUBE_CLIENT_SECRET = '<your OAuth client secret>'
   $env:YOUTUBE_REDIRECT_URI = 'http://127.0.0.1:8765/oauth2callback'
   ```

   Alternatively set `YOUTUBE_CLIENT_CONFIG_FILE` to an ignored Google OAuth
   client JSON file. Environment variables override file values.

7. Run the one-time flow:

   ```powershell
   python -m company.youtube auth
   ```

The authorization request uses PKCE, a CSRF state value, offline access, and a
consent prompt so Google returns a refresh token. Later commands exchange that
stored grant for a short-lived access token automatically.

## Operator commands

```powershell
python -m company.youtube status
python -m company.youtube channel --state-dir C:\path\to\company-state
python -m company.youtube videos --limit 10 --state-dir C:\path\to\company-state
python -m company.youtube analytics --days 28 --state-dir C:\path\to\company-state
python -m company.youtube analytics --days 28 --video-id VIDEO_ID --state-dir C:\path\to\company-state
python -m company.youtube smoke-test
```

The default analytics range ends yesterday and contains exactly `--days`
inclusive calendar days. `--end-date YYYY-MM-DD` overrides the end.

Every command can print normalized evidence without writing. Supplying
`--state-dir` appends one envelope under `youtube/evidence/` with distinct
`raw` and `normalized` fields, provenance, identity, retrieval time, date
range, and secret-free API-call telemetry.

## Existing Company OS analytics bridge

Channel-level evidence stays in the YouTube evidence ledger because the
analytics store is deliberately keyed to deliverables. Per-video evidence can
also become the existing `AnalyzedDeliverable` and `MetricObservation` records:

```powershell
python -m company.youtube analytics --days 28 --video-id VIDEO_ID `
  --state-dir C:\path\to\company-state --commit-analytics `
  --deliverable-id test-1 --kind short --format-id marble_race
```

The operator supplies `video` versus `short` and the format id; the connector
does not infer either from duration or title. Available readings are appended
with `OWN_ANALYTICS_API` provenance pointing to the YouTube evidence record.
Unavailable readings remain explicit in that source record and do not become
zero-valued observations.

Current normalized Analytics metrics are `views`,
`estimated_minutes_watched`, `average_view_duration_seconds`,
`average_view_percentage` (fraction 0–1), `subscribers_gained`,
`subscribers_lost`, `likes`, `comments`, and `shares`. The analytics bridge
converts estimated minutes watched to the existing `watch_time_hours` metric.
