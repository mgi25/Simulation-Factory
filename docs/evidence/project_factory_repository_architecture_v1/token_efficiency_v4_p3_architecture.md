# Token Efficiency V4 P3 — Deterministic Read-Once Semantic Context

Date: 2026-09-21

## Why P3

P2 successfully removed model-owned deterministic test loops, Bash loops, git loops, unrelated MCP and hidden paid retries. The remaining high-variance cost is repeated semantic reading.

Measured examples:

- one-file benchmark correction: 25 developer turns, 11 file reads, 10 repeated reads, 7 searches, 756,397 cache-read units;
- one-file YAML dependency repair: 8 developer turns, 2 file reads, 0 repeated reads, 1 search, 141,128 cache-read units.

The difference is not file count. It is how much discovery the model had to redo.

## Existing foundation

P2 already contains:

- a deterministic AST repository map;
- symbol line spans;
- reverse production-import relationships;
- reverse test relationships;
- deterministic free-text ranking;
- acceptance-criteria-to-test-anchor matching;
- bounded execution-context rendering.

P3 extends this existing system. It does not introduce embeddings, a vector database, an external service or another model.

## P3 design

### 1. Multi-span semantic compilation

Before a developer provider session, compile a small set of exact symbol spans from:

- authorized writable files;
- test files already authorized as context or declared required tests;
- acceptance criteria;
- objective text;
- deterministic symbol/body token overlap.

For each selected span retain:

- repository path;
- qualified symbol name;
- exact line range;
- deterministic reason;
- bounded excerpt;
- content digest.

The compiler is deterministic for a fixed checkout and work order.

### 2. One shared context budget

Compiled spans do not receive a second unlimited budget.

They share the existing execution-context budget. Selection stops before rendering exceeds the configured cap.

The compiler should prefer:

1. exact identifier phrase matches;
2. meaningful token overlap;
3. authorized writable-file spans;
4. required/declared test spans;
5. earlier line numbers as deterministic tie-breakers.

### 3. Read-once guidance, not a brittle prohibition

The developer briefing says:

- start from the compiled spans;
- do not rediscover the same span with broad grep/read;
- if information is missing, use Read on a targeted non-overlapping range;
- Read remains available.

This preserves quality if deterministic ranking misses a needed detail.

### 4. Persisted evidence and fingerprint

The runner writes the compiled context artifact before launching the provider session.

Evidence includes:

- compiler version;
- source commit;
- selected spans;
- rendered character count;
- truncation/budget state;
- deterministic fingerprint.

This lets benchmarks compare what the model was actually given, rather than inferring it from transcript behavior.

### 5. No authority role

The compiler cannot authorize a path.

It may only compile:

- paths already writable under the immutable work order; or
- read-only context/test paths already present in the work order's effective context / required test set.

If a path is absent from both surfaces it cannot appear as a compiled span.

### 6. Fallback

If no useful semantic spans are found:

- preserve P2's current bounded file-neighborhood/excerpt behavior;
- do not fail the work order;
- do not widen search or authority.

If useful spans are found:

- prefer them over generic first-symbol excerpts to avoid duplicated prompt content.

### 7. P2 controls remain intact

P3 does not change:

- consumer developer tool filtering;
- MCP isolation;
- provider session accounting;
- backend-stop behavior;
- report-repair accounting;
- runner-owned tests;
- independent reviewer;
- gate suites;
- CEO merge/deploy/publish controls.

## Performance strategy beyond P3

A more advanced and cheaper system is achievable without lowering quality by stacking deterministic controls:

### P3 — semantic read-once context
Reduce discovery turns and repeated reads.

### P4 — content-addressed repository intelligence cache
Fingerprint repository-map and compiled-span artifacts by commit/path digest so repeated work orders reuse local analysis at near-zero model cost.

### P5 — adaptive model routing
Use local complexity evidence to keep routine work on the standard tier and escalate only when deterministic signals justify it. Never downgrade review/gate requirements.

### P6 — deterministic reviewer pre-adjudication
Run all mechanically checkable review criteria before the reviewer model starts and send the reviewer only unresolved semantic questions plus the measured diff. This reduces reviewer tokens without letting deterministic checks substitute for independent review.

### P7 — benchmark-driven resource optimizer
Use observed task telemetry to recommend context/turn/model ceilings, but keep ceilings monotonic with risk and preserve CEO authority.

The long-term target is not the cheapest possible call. It is the lowest provider spend that still produces the same or better deterministic quality evidence.

## P3 acceptance boundary

Before any paid P3 benchmark:

- compileall green;
- focused runner/context tests green;
- all canonical Company OS required suites green;
- integration gate READY;
- no new dependency;
- no production dependency;
- no authority widening;
- exact P2 provider/tool controls unchanged.

No canonical merge is authorized by this design.
