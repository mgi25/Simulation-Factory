# Job C — stopped at the schema pre-flight check, never submitted

See `docs/company_os_supervised_burnin_b_and_c.md`, Part 3, for the full finding.

Summary: the CEO's brief for Job C (`company/finance/usage_cost.py`, deduplicating
provider usage records that represent the same measured response/event) required
verifying, before any implementation, that the actual telemetry schema carries a stable
existing identifier suitable for deterministic deduplication. It does not:
`ai_platform.usage.ResourceUsageRecord` carries no per-event identifier, and the only
identifier-shaped field anywhere near it (`UsageObservation.usage_ref`) is supplied by the
caller from the store's file-sequence position, not read from the record or the provider.
`usage_fingerprint` is a content digest, not an event identity, and would both miss the
brief's own cited real case (non-identical rows repeating one response) and wrongly merge
independent, coincidentally-identical measurements.

Per the CEO's explicit instruction ("If no stable identifier exists: STOP rather than
inventing one"), no request was submitted, no work order was created, no dry-run intake
was even run (the schema check gates implementation *before* intake), and no developer or
reviewer session was spawned. Nothing in this directory is execution evidence.
