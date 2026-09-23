# Company OS / Project Factory — Speed-First Master Handoff

**Date:** 23 September 2026  
**Repository:** `mgi25/Simulation-Factory`  
**Purpose:** operational handoff for finishing Company OS quickly while reducing whole-task model/token waste. This file is intentionally self-contained so a new chat can continue without restarting the research.

## Status vocabulary

- **CONFIRMED** — observed in repository state or validation evidence.
- **DECIDED** — current sequencing/architecture decision; may not be implemented yet.
- **PLANNED** — approved direction after prerequisites.
- **EXPERIMENTAL** — must beat the current baseline before adoption.
- **R&D BACKLOG** — deliberately postponed so it does not delay Company OS.
- **FORBIDDEN** — cannot be delegated to learning without a future governance change.

## Current decision

Project Factory has two goals at the same time:

1. Finish the AI Company / Company OS as fast as possible.
2. Reduce the token, model-cost, context, retry and execution waste that makes it expensive to finish.

Broad optimization research is **not** the default activity anymore. We have enough research to act. Use roughly **80–90% of engineering effort on completing Company OS** and **10–20% on high-payback efficiency infrastructure**.

A useful rule is:

`optimization payback = expected remaining-development savings / implementation + validation + maintenance cost`

If payback is weak or uncertain, defer the idea to R&D.

## Confirmed repository/P5 state

**CONFIRMED**

- P5 branch: `project-factory-token-efficiency-v4-p5`
- P5 head: `533ae4e4f03f6faf10b5b316ada7edcabb49972d`
- Head message: `docs: explain p5 gated economy downshift`
- Latest supplied validation: **269 runner-focused tests passed**, **11/11 canonical Company OS suites green**, integration gate returned with **zero technical blockers**.
- P5 permits an economy downshift only when deterministic first-attempt evidence proves sufficient localization/low risk. Standard remains the normal recommendation.
- The missing P5 item is the **matched real-work benchmark**. Do not claim a P5 percentage saving until it is run.

Live GitHub state checked while preparing this handoff:

- current `main`: `d2a30027aeaf044c3e9d03ef961b8f8331a16140`
- P5: `533ae4e4f03f6faf10b5b316ada7edcabb49972d`
- the branches are **diverged**
- P5 was reported **89 commits ahead and 10 behind** current `main`
- merge base: `65df08a3e22d692d2783ab6004ce6f3d4046f54e`

Therefore do **not** assume P5 can be fast-forwarded into `main`. Preserve P5 as a benchmark/control point until its matched benchmark is frozen. Reconcile with current main before any eventual integration.

## Why this optimization work exists

Historical observed telemetry showed that a nominally successful developer stage could hide a failed/budget-stopped paid session before a later successful one.

Earlier recorded stage (not a matched experiment):

- provider cost: `$3.4722695`
- cache read: `2,111,924`
- cache create: `124,470`
- output: `65,525`
- two paid developer sessions, including a budget-stopped first session

Accepted P3C reference run (also not a causal comparison to the earlier task):

- developer attempts: 1
- developer turns: 12
- cache read: `222,727`
- cache create: `25,041`
- output: `6,448`
- developer cost: approximately `$0.4291`
- reviewer corrections: 0
- required suites: 11/11
- final state: READY

The lesson is permanent: **measure whole accepted-task economics and include failed/retried/budget-stopped work.**

## Primary optimization objective

Minimize **whole-task paid model resources per accepted deliverable**, subject to quality, deterministic validation, independent review, safety and governance staying at or above baseline.

The resource vector includes more than tokens:

- paid input/cache/output and provider cost
- wall time
- local CPU/GPU time
- retries/rework
- test compute
- reviewer corrections
- READY/reliability rate
- risk/governance constraints

A smaller prompt that causes another developer attempt is not an efficiency win.

# Immediate roadmap

## WP0 — Preserve/reconcile state

- Confirm live `main`, P5 and benchmark base SHAs.
- Do not merge them yet.
- Identify the accepted P3C work order used as the control.
- Produce an immutable benchmark manifest.

**Exit:** reproducible matched inputs.

## WP1 — Close P5 with a matched benchmark

Compare:

- **P3C control:** standard model + accepted P3C failure-guided context
- **P5 challenger:** economy downshift only where P5 permits; otherwise identical

Freeze the same base SHA, task text, acceptance criteria, authority, tools, model/settings where controllable, attempt ceiling, reviewer, tests, timeout and environment.

Measure all developer/reviewer subprocesses, including failures.

Required outputs:

- benchmark manifest
- per-session provider telemetry
- retries/stop reasons
- deterministic validation
- reviewer result
- READY/failure
- whole-task cost/tokens/cache/turns/latency

**Kill condition:** material READY/reviewer/quality regression.

## WP2 — Immutable telemetry + minimal typed IR

Build this early because future learning/OPE data cannot always be reconstructed later.

Minimum telemetry:

- task/work-order ID and repo/base SHA
- task family, risk/novelty/scope
- allowed actions/tools/model tiers
- all developer/reviewer subprocesses
- turns, uncached input, cache read/write, output, provider cost
- local compute when applicable
- tool calls grouped by read/search/test/edit/git
- raw tool size vs delivered tokens
- context object IDs and rereads/expansions
- tests and wall time
- retries/stop reasons/escalations
- reviewer findings
- final deterministic gate and READY/failure
- safety violations (must remain zero)

Introduce small typed structures, not a giant rewrite:

- `TaskIR`
- `EvidenceIR`
- `ContextObject`
- `ValidationEvidence`
- `ExecutionReceipt`

Learning may later consume these structures, but they are deterministic records first.

## WP3 / P6A — Deterministic efficiency core

### Cache-stable prompt compiler

Compile prompts deterministically:

```
CACHE-STABLE PREFIX
constitution / policy schema
role
stable tool schemas
stable output contract
stable repo capsule/map
compiler/schema version
--------- cache boundary ---------
DYNAMIC SUFFIX
work order
current authority instance
current repo SHA/state
current diff
failures
new context objects
iteration state
```

Tests should ensure byte-identical stable prefixes for identical inputs, deterministic tool ordering/canonical serialization, no volatile timestamps/UUIDs before the cache boundary, and provider-specific rendering behind one internal abstraction.

### Reversible evidence compression

Keep exact raw tool/test output in a local evidence store. Give the model a compact deterministic view plus an expansion handle.

Never silently lossy-compress exact source, diffs, assertions, permissions, acceptance criteria or mandatory safety evidence.

Benchmark **whole-task** impact, not just compression ratio.

### Content-addressed read-once context

Reuse Git/blob identity.

First delivery:

```
OBJECT <id>
<bounded exact content>
```

Unchanged repeat:

```
REF <id>
```

Explicit request:

```
EXPAND <id>
```

Goal: unchanged reread cost approaches zero without extra mistakes/retries.

### Minimal role-specific tool surface

Expose only tools required for the task/role. Do not load a huge MCP/tool catalog by default.

## WP4 / P6B — Canonical code objects + hybrid retrieval

Use semantic code-object identities rather than overlapping arbitrary chunks.

A canonical identity should be derived from repository ID, Git blob SHA, language, qualified symbol/object identity, kind, definition fingerprint/span and schema version.

Possible views/companions:

- signature
- exact definition
- callers/callees/references
- associated tests
- failing traces
- current diff
- docs/summary

Generate candidates from several complementary channels:

- exact identifier/string match
- BM25/lexical
- AST
- LSP definitions/references
- dependency/call graph
- traceback/failing tests
- test ownership/impact
- Git/source state
- optional embeddings only when they improve vague natural-language retrieval

Start ranking with deterministic weighted/RRF methods. Learn a ranker only after enough accepted trajectories exist. Embeddings are never repository truth.

External challengers: Aider repo-map ranking, Serena/LSP read-only retrieval, grepai semantic search, VITAL-RAG-style object dedup. FastContext is design inspiration only; literal runtime subagents conflict with the validated no-subagent rule.

## WP5 / P6C — Fast development validation + Experience Store

Use selective/impact-based tests **during iteration**:

`changed symbols -> impacted tests -> fast feedback`

But acceptance remains:

`full required canonical suites -> independent review -> gate -> READY`

Selective testing never replaces the final suite.

Persist successful **and failed** trajectories. Failed cheap paths and rejected experiments are useful negative knowledge.

Start exact digital-twin replay for deterministic components now (compression, rankings, test selection, prompt construction). Model-routing counterfactuals remain unknown unless later data gives valid action support.

## WP6 — Return to full-speed Company OS completion

After the small P6 foundation is measured and stable:

- move the majority of engineering capacity back to unfinished Company OS capabilities
- use P6 infrastructure by default
- let telemetry reveal the next dominant bottleneck
- research/optimize only that bottleneck

Examples:

- retrieval dominates -> improve retrieval
- cheap-model fallback causes replay -> improve/disable routing for that task family
- repeated workflows dominate -> investigate procedure/workflow compilation
- reviewer cost dominates -> add stronger deterministic verification
- hosted inference dominates at scale -> evaluate self-hosting

# Local AI / Ollama decision

**PLANNED, not the first critical-path task.**

Local AI may be prepared in parallel as a small sidecar if it does not delay WP0–WP5. It enters live work only if it improves **whole accepted-task economics**.

Good early jobs:

- repository/task classification
- candidate-symbol ranking on a bounded set
- log/test-output summarization with exact pointers
- document summarization
- context scoring
- anomaly classification
- eventually localized low-risk patches with strong deterministic tests

Bad early jobs:

- permissions/authority
- finance/security/governance decisions
- production mutation
- novel architecture
- replacing final review
- large unbounded coding tasks that trigger expensive cloud replays when wrong

Integrate local inference through a provider boundary, not by hard-coding Ollama. That preserves future Ollama/llama.cpp/vLLM/SGLang options.

# Later adaptive/R&D roadmap

These are intentionally postponed until the deterministic foundation produces trustworthy trajectories:

- supervised context/model-value predictors
- learning-to-rank
- Value of Information context acquisition
- Value of Computation across retrieval/tests/models/reasoning
- dynamic token/reasoning budgets
- contextual bandits
- conformal risk calibration around cheap routing
- optimal stopping
- workload-level budget allocation
- hierarchical memory: working/episodic/semantic/procedural
- memory usefulness/expiry/provenance and memory-on vs memory-off tournament
- procedure/workflow compilation from repeated successful trajectories
- belief-state/POMDP-style control
- stronger deterministic verification: property/differential/metamorphic tests, fuzzing, mutation testing, symbolic/concolic execution, formal methods where justified
- global company resource scheduler
- self-hosted inference/KV reuse/speculative decoding/hardware-aware scheduling
- speculative safe read/test execution

The ultimate system may become a **Self-Optimizing Cognitive Compute System**: deterministic authority + typed/incremental compiler + scheduler + task-local metacontroller + multi-fidelity compute allocator + verification kernel + experience compiler/digital twin.

Do not freeze that long-term controller design before simpler layers prove what the real bottlenecks are.

# External projects are challengers, not dependencies

Important candidates already researched:

- RTK — command-specific shell compression
- sqz — content-addressed reread references
- tare — reversible/cache-aware compression
- LeanCTX — broad context/wire-path optimization reference
- Aider repo map — token-budgeted structural ranking
- Serena — LSP/symbol navigation
- grepai — semantic code retrieval
- VITAL-RAG — canonical code-object evidence budgeting
- SWE-Pruner — goal-conditioned source pruning, shadow only initially
- LLMLingua — prose/history compression, not exact code/policy
- Mem0/OpenMemory — later persistent-memory challenger
- Graphiti/Zep/Cognee — later organizational-memory references
- GPTCache — narrow state-keyed read-only semantic cache
- MemoryBench / VibeMemBench — memory evaluation methodology
- RouteLLM / PILOT / WISERouter — later routing references
- conformal routing — later calibrated cheap-route safety layer
- ContextBudget — sequential context control reference
- NameRTS / stet — selective test ideas
- LMCache / CacheScout / CacheSlide — only after self-hosting
- PASTE/speculative tools — later latency optimization

Never multiply published savings from unrelated systems. Reproduce benefits on Company OS workloads.

# Permanent guardrails

- Learning never creates authority.
- Git/policy/permissions/production/approval/finance truth remains deterministic.
- Final canonical validation is never replaced by selective development tests.
- Independent review remains until evidence justifies a narrower scope.
- Exact source/diffs/assertions/permissions/acceptance criteria are not silently lossy-compressed.
- Raw evidence remains retrievable.
- Memory is advisory, never current-state authority.
- Model/resource routing is policy-filtered before economic optimization.
- Failed/retried/budget-stopped work stays in accounting.
- Unknown counterfactuals remain unknown.
- External projects are challengers before dependencies.
- Learned strategies use shadow/champion-challenger promotion.
- No runtime subagents unless governance explicitly changes.
- No autonomous production mutation.
- Self-improvement never deploys its own policy changes.

# Primary metrics

Always report quality/safety together with economics.

- READY rate
- developer attempts/turns
- reviewer corrections/findings
- uncached input
- cache read/write
- output tokens
- whole-task provider cost
- paid token-equivalent
- wall time and time-to-first-retained edit
- local compute
- tool calls
- raw vs delivered tool tokens
- reread tokens / unique-content ratio
- cache hit ratio
- escalations
- tests and test time
- retrieval Recall@token/ranking quality where relevant
- stale/unsupported memory rate where relevant
- safety violations (must remain zero)

Promotion requires non-regressive quality, intact governance, material whole-task improvement, reproducibility, justified complexity and a rollback path.

# Research policy from now on

Broad deep research becomes **event-triggered**.

Resume research when telemetry shows a dominant bottleneck, an optimization plateaus, a provider/runtime materially changes, a major technique directly targets a measured problem, security/governance needs new evidence, self-hosting becomes economically justified, or the project is ready for advanced learning/memory.

The R&D loop should be:

`signal -> candidate -> isolated reproduction -> matched benchmark -> efficiency/quality/safety review -> champion/challenger -> adopt/reject/defer -> retain negative knowledge`

# What not to do

Do not:

- restart broad research before the P5 benchmark without a critical new unknown
- install all optimization/memory projects together
- replace Company OS with another agent framework
- make embeddings repository truth
- make memory authority
- allow learning to explore production/finance/security/governance authority
- use lossy compression on exact modification/approval evidence
- replace final suites with selective tests
- force local AI first on every task
- claim context reduction equals bill reduction
- claim a universal “best in the world” architecture without matched evidence
- merge the diverged P5 branch into current main without reconciliation/full validation

# New-chat continuation protocol

A future assistant should:

1. Read this handoff completely.
2. Inspect the **current** repo; do not assume these SHAs remain current.
3. Preserve CONFIRMED/DECIDED/PLANNED/EXPERIMENTAL/R&D/FORBIDDEN distinctions.
4. Determine whether the P3C-vs-P5 matched benchmark has been completed.
5. Continue from the first unfinished work package.
6. Do not redo broad research unless a measured bottleneck/new unknown requires it.
7. Keep the speed-first effort split unless telemetry gives a better allocation.
8. Keep deterministic authority, final tests, independent review and full retry accounting.
9. Treat Ollama/local AI as an experiment until whole-task evidence proves value.
10. Do not merge major architecture into production without the existing authorization/gate process.

Suggested new-chat prompt:

> Read the Company OS / Project Factory Speed-First Master Handoff completely. Inspect the current `mgi25/Simulation-Factory` repository and reconcile live Git state with the P5/main state recorded here. Do not redo completed work or restart broad research. Our priority is to finish Company OS as fast as possible while implementing only high-payback resource optimizations. Determine whether the P3C-vs-P5 matched benchmark is complete, continue from the first unfinished work package, preserve deterministic authority/validation/review guardrails, and provide evidence for every claimed efficiency improvement.

# Final operating thesis

Project Factory should win by **eliminating unnecessary cognition, reusing verified computation, buying expensive intelligence only where it changes the outcome, and learning from every accepted and failed task without allowing learned systems to become authority.**

For the current schedule:

**Stop researching by default, close P5, build the small high-payback P6 foundation, then finish the AI Company at full speed while telemetry determines what optimization is actually needed next.**
