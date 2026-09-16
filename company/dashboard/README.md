# Company CEO dashboard

This package is a deterministic, read-only projection over canonical Company OS records.
It does not approve, reject, spend, hire, archive, publish, merge, repair, or schedule
anything. Its JSON contains compact references and fingerprints, never copied source
record bodies.

## State layout

`build_snapshot(<company-state>)` expects canonical stores below one explicit root:

```
<company-state>/
  runtime/       # ExecutionStore and ResourceUsageStore root
  research/      # ResearchStore root
  analytics/     # AnalyticsStore root
  finance/       # FinanceStore root
  workforce/     # WorkforceStore root
  organization/  # OrgIntelligenceStore root
```

`CompanyStatePaths` can point each source at a different existing directory. The
separation matters because several subsystem stores intentionally use the same directory
names for different record types. Missing directories and empty stores are reported as
missing data; they are never converted to zero.

## CLI

```
python -m company.dashboard build --state-dir state/company --output-dir state/dashboard --as-of 2026-09-17
python -m company.dashboard show --output-dir state/dashboard --snapshot company-state-0123456789abcdef
```

Build writes a canonical JSON snapshot and compact text brief beneath the caller-supplied
output directory. Files are created exclusively. Repeating identical output is a no-op;
differing content under the same snapshot ID is refused.

Snapshot identity includes the explicit `as_of` date. Source freshness is `current`,
`stale`, or `unknown`; absent recheck metadata stays unknown. Snapshot diffing compares
record identities, fingerprints, freshness, decision states, and attention states. It
does not infer significance from prose.

