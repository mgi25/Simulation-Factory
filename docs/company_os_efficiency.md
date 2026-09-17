# Company OS efficiency measurement

Company OS records efficiency as immutable, machine-readable records under the
existing caller-supplied execution state directory:

```text
execution/efficiency/<task>/000001.json
execution/tool_outputs/<task>/000001.json
```

`EfficiencyStore` is a typed facade over `ExecutionStore.append_extension()`;
it uses the same exclusive-create, append-only convention as packets,
authorities, expansion decisions and receipts without introducing a reverse
runtime import. An efficiency record can name a packet fingerprint and attempt;
the facade refuses the record if that link does not match persisted execution
history. Raw tool output is retained in its artifact even when a future
compressor supplies a smaller context-facing representation.

## Research capsule split

`company-research-intelligence` owns durable evidence, confidence, synthesis,
reference-analysis and scoring contracts. `company-research-operations` owns
ingestion, discovery, screening, batching, stop rules and resource accounting.
Operations depends on core; core does not depend on operations. Consequently a
reference-analysis task receives core knowledge without operational procedure,
while an ingestion/batch task receives both through normal dependency closure.

## Measurements and provenance

`EfficiencyRecord` captures task/run identity, capabilities and capsules,
capsule/context/packet sizes, manifest and packet fingerprints, selected and
opened repository files, tool calls/output, cache results, expansion decisions,
latency, model, tokens and cost. Character counts use Python Unicode code
points; byte counts use UTF-8.

Token and cost values always declare one source:

- `provider_reported`: copied from a provider response.
- `estimated`: computed by a named method. The dependency-free benchmark
  fallback is `ceil(UTF-8 bytes / 4)` and is never labelled provider usage.
- `unavailable`: numeric fields are `null` and a reason is mandatory.

Monetary estimates require a `rate_ref`; no provider price is hardcoded. This
keeps the existing Finance rate-card and evidence rules authoritative.

## Benchmark modes

Run the credit-free suite with:

```text
python -m company.efficiency --repo . --output efficiency.json
```

The six fixtures cover a one-capsule task, dependency closure, core research,
repository work, approved/denied context expansion and repeated warm-cache
execution. They invoke no LLM or network service.

- `baseline` loads every registered capsule plus the scenario's explicit file
  candidates.
- `capsule_optimized` uses deterministic capsule selection/dependency closure
  and only candidate files related to selected ownership boundaries.
- `full_raw_context` adds an explicit, controlled list of raw files. It never
  scans the repository or treats a directory/glob as permission to load it.

Percent reductions are `null` when either measurement is unavailable or the
baseline is zero. Benchmark output contains both raw records and comparisons;
it does not fabricate latency, model, monetary cost or provider token usage.

## Optional integration boundaries

`CodeIntelligenceProvider` accepts symbol, caller, dependency, path and likely
file queries. The default `ReferenceRepositoryProvider` preserves current
behaviour: it validates explicit repository-relative file candidates without a
scan. Symbol-graph requests report unavailable. Graphify is not installed or
simulated; a future adapter can implement the same protocol.

`ToolOutputCompressor` transforms raw output only for model context.
`ToolOutputArtifact` always retains command, exit status, failures, warnings,
summary, artifact references and raw output. RTK is not installed or simulated;
without an injected compressor, context output equals raw output.

`check_reuse()` is the deterministic minimalism check. It records that a change
considered, in order: an existing Company OS capability, project utility,
standard library, installed dependency, small implementation and large
subsystem. It emits a measurable signal and never makes a separate model call
or blocks legitimate work.

## Dashboard consumption

`summarise_efficiency()` exposes a stable aggregate with total runs; average
input/output tokens and context bytes; context reduction; known cost; cache hit
rate; expansion rate; average repository reads; and tool-output reduction.
Individual append-only records remain the time series for trend views. Missing
measurements stay `null`, and mixed or incomplete monetary records do not
produce a total. Provider-reported and estimated token runs have separate
counts; aggregate token averages are `null` rather than mixing sources.
