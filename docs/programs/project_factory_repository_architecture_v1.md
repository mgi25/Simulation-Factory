# Project Factory Repository Architecture V1

**Status:** authorized discovery and design program; no canonical merge authorized  
**CEO authorization date:** 2026-09-21  
**Baseline:** `main` at program branch creation  
**Program branch:** `project-factory-repository-architecture-v1`

## 1. CEO objective

Prepare Project Factory for sustained codebase growth without allowing repository size to cause proportional growth in architecture ambiguity, AI context cost, repository rediscovery, maintenance cost, or regression risk.

This program must improve both:

1. **technical architecture** — coherent subsystem boundaries, ownership, dependency direction, lifecycle clarity, testability, and future extensibility; and
2. **AI operating efficiency** — minimum sufficient context, deterministic repository intelligence, token/resource attribution, low rework, low duplicated reads/searches, and evidence that Company OS is economically useful rather than bureaucratic overhead.

The objective is not to make the repository look tidier. It is to make future work cheaper, safer, easier to locate, easier to review, and easier to extend.

## 2. Operating principles

- No big-bang rewrite.
- No folder movement merely for aesthetics.
- No speculative abstraction for hypothetical future products.
- Preserve Race #2 V33.1 and other frozen release evidence.
- Preserve production/Company OS separation.
- Prefer executable architecture rules over prose-only conventions.
- Prefer deterministic tools over model inference where the answer can be derived.
- Preserve history, but keep current architecture distinguishable from historical evidence.
- Every migration step must be reversible, independently testable, and measured.
- Exact AI usage is recorded when the backend exposes it; unavailable measurements are marked **UNAVAILABLE**, never estimated.
- Canonical/main promotion, workforce activation, new paid recurring services, destructive cleanup, and major architecture merge remain CEO-reserved.

## 3. Company ownership

### Chief Architect — accountable owner
Owns current-state architecture discovery, target-state architecture, dependency rules, public/internal boundaries, migration sequencing, and architectural fitness functions.

### AI Efficiency Platform Engineer — mandatory co-owner
Owns AI/resource accounting and optimization across the entire program, including Company OS overhead itself.

### Engineering Delivery Manager
May coordinate bounded routine implementation work that falls inside separately authorized work orders.

### Software Review Engineer
Must independently review implemented engineering changes and the evidence supporting them.

### HR / Organizational Intelligence
Must evaluate whether the recurring repository-maintenance capability justifies a permanent `repository_architecture_steward` role. This program does **not** activate that role merely by proposing it.

## 4. Phase A — current-state architecture discovery

Before moving production code, produce a machine-grounded inventory of the repository.

Required outputs:

- top-level subsystem inventory;
- active / supported / legacy / experimental / archived lifecycle classification;
- dependency graph and dependency-direction violations;
- subsystem ownership map;
- unowned and multiply-owned modules;
- public vs internal interface inventory where derivable;
- test/benchmark coverage map;
- complexity and oversized-module hotspots;
- duplicate abstractions and parallel implementations;
- stale/dead-code candidates, without deleting them;
- documentation/current-state drift;
- known branch/test fixture dependencies that cleanup must preserve;
- repository-discovery and context-cost hotspots;
- current technical-debt register consolidated from existing evidence.

Architecture discovery must use existing deterministic repository intelligence before introducing a new indexing dependency.

## 5. Phase B — target-state design

The Chief Architect must propose a future-scale architecture that can accept new formats, media workflows, analytics, research, and company capabilities without predicting specific future products.

The design should define stable seams such as:

- format/domain logic;
- simulation;
- presentation/cinematography;
- rendering/export;
- production/QC;
- experiment metadata;
- analytics;
- research/intelligence;
- Company OS/control plane;
- AI platform/context infrastructure.

Required design artifacts:

- target subsystem graph;
- allowed dependency directions;
- forbidden dependency edges;
- subsystem ownership contract;
- lifecycle policy;
- public API / internal API policy;
- archive/deprecation policy;
- architecture decision record policy;
- machine-readable subsystem metadata;
- architecture fitness functions that can fail CI;
- incremental migration plan with rollback points.

A target-state proposal is not permission to perform a major architecture rewrite or merge it to canonical.

## 6. Repository Architecture Steward evaluation

The program must evaluate this candidate recurring capability:

`repository_architecture_steward`

Candidate mission:

> Maintain a coherent, discoverable, dependency-bounded, AI-efficient repository as Project Factory grows, under architecture defined by the Chief Architect.

Capabilities to evaluate:

- repository_governance
- codebase_health
- module_lifecycle
- dependency_hygiene
- dead_code_analysis
- architecture_conformance
- repository_discoverability

The evaluation must answer whether this should be:
- a permanent role;
- a responsibility added to an existing role;
- a deterministic tool/workflow rather than an AI role; or
- a temporary specialist only.

## 7. AI usage and efficiency telemetry

AI efficiency is a first-class deliverable, not a closing note.

For each AI-backed stage, capture where available:

- provider/model;
- input units/tokens;
- output units/tokens;
- cache-read units;
- cache-creation units;
- prompt/instruction/context characters;
- model turns;
- tool events/calls;
- repository reads;
- unique repository reads;
- repeated reads;
- searches and repeated searches;
- files read but not changed;
- retries/corrections;
- wall time;
- monetary cost when exposed by the provider;
- result state;
- reviewer result;
- deterministic test/gate result.

Classify resource use, where evidence permits, into:

- planning/coordination;
- repository discovery;
- architecture reasoning;
- implementation;
- review;
- deterministic validation;
- rework;
- redundant/avoidable work;
- reporting/handoff.

Do not infer exact ChatGPT/consumer-plan token usage when the platform does not expose it. Record plan-level usage as **UNAVAILABLE** unless measured by an authoritative source. Provider/session telemetry may still be used where available.

## 8. Efficiency scorecard

At minimum calculate:

- total AI resource cost per accepted verified change;
- total Company OS coordination/review overhead;
- developer exploration cost;
- reviewer exploration cost;
- first-pass acceptance rate;
- correction/retry rate;
- resource spend on rejected work;
- repeated-read/search rate;
- context size per stage;
- cache reuse;
- wall time to accepted result;
- regressions introduced;
- durable knowledge/tooling created.

A lower token count is not automatically better if quality or reliability falls.

## 9. Company OS vs direct-session benchmark

The program must test whether Company OS produces enough value to justify its overhead.

Use matched real engineering tasks, not invented toy tasks.

For each matched pair:

- same base commit;
- same objective;
- same allowed scope;
- same acceptance criteria;
- same required tests;
- same quality bar.

Compare:

**A. Direct engineering session**
versus
**B. Company OS routed workflow**

Measure total resource use across all Company OS stages, not only the developer.

Use multiple matched tasks where practical; do not generalize from one noisy run.

Interpretation must include both resource cost and outcomes:
- accepted quality;
- defects/regressions;
- corrections;
- reviewer findings;
- architecture violations;
- time;
- reusable knowledge produced.

If Company OS is more expensive without compensating quality/reliability benefit, simplify it. The goal is to evaluate the system, not prove it is good.

## 10. Workflow-routing outcome

The AI Efficiency Platform Engineer must determine whether one workflow fits every task.

The final recommendation may differentiate, for example:

- tiny/local low-risk work → direct/lightweight path;
- normal bounded engineering → compact Company OS path;
- high-risk cross-subsystem work → architect + implementation + independent review;
- major architecture → CEO decision gate.

Any such routing must be evidence-backed rather than assumed.

## 11. Initial success criteria

The discovery/design milestone succeeds only if:

1. current architecture can be explained from a compact authoritative model rather than reconstructed from historical chats/docs;
2. every active production/company subsystem has an explicit lifecycle classification and owner or an explicit ownership gap;
3. dependency direction can be machine-checked for at least the most important boundaries;
4. existing capsule/ownership gaps, including currently unclaimed modules, are accounted for;
5. an incremental target architecture and migration sequence exist without a big-bang rewrite;
6. AI usage is attributable by stage and role wherever telemetry exists;
7. redundant reads/searches and major resource hotspots are identified;
8. a matched Company OS vs direct-session benchmark design is frozen before observing its results;
9. the Repository Architecture Steward capability receives an evidence-backed organizational recommendation;
10. no frozen release or canonical production behavior is changed merely to complete the audit.

## 12. Decision gates

### Gate 1 — discovery complete
Chief Architect presents current-state findings and target-state proposal.

### Gate 2 — architecture decision
CEO decides which major architecture changes, if any, are approved.

### Gate 3 — incremental migration
Approved architecture changes are decomposed into reversible bounded work orders.

### Gate 4 — economic validation
AI Efficiency Platform Engineer reports whether the architecture and Company OS reduce total cost per accepted verified outcome.

### Gate 5 — canonical promotion
Any major architecture merge to `main` remains an explicit CEO decision.

## 13. Required final executive report

The final program report must state:

- what the repository looked like before;
- what actually changed;
- what intentionally did not change;
- test/gate evidence;
- architecture fitness results;
- AI resource use by stage and role;
- where resource use was wasted;
- before/after efficiency;
- Company OS vs direct-session result;
- whether Company OS should be kept, simplified, or routed selectively;
- whether a Repository Architecture Steward should become permanent;
- remaining technical/organizational debt;
- recommended next phase;
- CEO decisions still required.

The program is successful only if Project Factory becomes easier to extend **and** we can demonstrate whether the process used to improve it was itself efficient.
