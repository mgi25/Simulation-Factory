# Company OS v1 — real-evidence acceptance report

Bootstrap SHA: `f49df25c2072d36431daca3d802fb4126593f48c`
Branch: `company-os-v1-real-evidence-acceptance`
Acceptance date: 2026-09-17
Final acceptance status: **ACCEPTED_WITH_MISSING_EVIDENCE**

This run does not add architecture. It proves the integrated system works on
genuine evidence and establishes the resource baseline the CEO needs before any
forecasting. Nothing was optimised; measurement came first, as instructed.

Private state — the acceptance state directory, the dashboard snapshot and the
CEO brief — lives outside the repository and is **not** committed. This document
is the sanitized record.

---

## 1. Test result

`pytest tests/test_company*.py` at the bootstrap SHA:

```
1370 passed in 101.35s
```

`git diff --check`: clean, exit 0.

The 11 gate-required suites were also run individually, so the evidence handed
to the gate is per-suite rather than an aggregate assertion:

| suite | selected | failed |
|---|---:|---:|
| tests/test_company_analytics.py | 160 | 0 |
| tests/test_company_dashboard.py | 32 | 0 |
| tests/test_company_execution_transport.py | 7 | 0 |
| tests/test_company_finance.py | 123 | 0 |
| tests/test_company_integration_gate.py | 88 | 0 |
| tests/test_company_org_intelligence.py | 119 | 0 |
| tests/test_company_os_ai_platform.py | 46 | 0 |
| tests/test_company_os_capsules.py | 66 | 0 |
| tests/test_company_os_knowledge.py | 26 | 0 |
| tests/test_company_runtime.py | 20 | 0 |
| tests/test_company_workforce.py | 93 | 0 |

Two production-environment suites were run and classified as such
(`company_os: false`), which is what `health.production_failures_separated`
had been unable to see: `tests/test_production_qc.py` 43 passed,
`tests/test_production_delivery.py` 38 passed.

## 2. Production Integration Gate

Run against the repository three times: once as the gate has been run before
(no state directory), once against the populated acceptance state, and once
with production-suite results classified. Policy v1, 34 required + 4 advisory.
No check was weakened.

| run | readiness | pass | fail | unknown | blockers |
|---|---|---:|---:|---:|---:|
| suite evidence only | READY | 34 | 1 | 3 | 0 |
| + populated state dir | READY | 34 | 1 | 3 | 0 |
| + production suites classified | READY | **35** | 1 | 2 | 0 |

Final report id: `integration-readiness-2026-09-17-8b2766a03589e6aa`.
All 34 required checks pass in every run. `authorizes_production_integration:
false` — by design, not a defect. The gate reports that the technical
conditions hold; wiring Company OS into production stays a separate CEO
decision.

**What the populated state directory changed.** The state-dependent advisory
unknowns did not flip to pass, but their reason changed, and the change is the
finding: they moved from *untested* to *measured and empty*.

| check | before | after |
|---|---|---|
| `executive.decision_queue_preserves_source_refs` | "no company state directory was supplied" | "the supplied state directory produced an empty decision queue" |
| `workforce.capability_gaps_visible` | "no company state directory was supplied, so there is no coverage to read" | "the supplied state directory holds no role records, so coverage is unknown" |

Both remain UNKNOWN, correctly: an empty decision queue proves nothing about
what a populated one carries. They will resolve when the company records its
first CEO decision and its first role specification — not when the gate is
re-run.

`health.production_failures_separated` did resolve, UNKNOWN → PASS, on real
classified production-suite evidence.

**One advisory failure stands, pre-existing and non-blocking:**
`architecture.subsystem_ownership_bounded` — 7 Company OS modules that no
capsule claims:

```
company/workforce/__init__.py     intelligence/__init__.py
company/workforce/__main__.py     knowledge/__init__.py
company/workforce/common.py       knowledge/company_os/__init__.py
company/workforce/errors.py
```

Not fixed here: this run was instructed to measure rather than optimise, and
the repair is a capsule-authoring decision, not a correctness defect. It is
advisory and does not block readiness. It interacts with the capsule dependency
cap noted below and should be scheduled deliberately.

## 3. Real execution evidence

No persisted Company OS task history existed anywhere on this machine — the
subsystems had been built and tested but never run against a real state
directory. So one bounded, read-only task was taken through the full runtime
workflow.

```
TaskSpecification → classification → routing → context manifest
  → SessionPacket + ExecutionAuthoritySnapshot
  → (execution by the external session)
  → SessionReceipt → validation → ResourceUsageRecord + HandoffArtifact
```

| | |
|---|---|
| task | `acceptance-2026-09-17-capsule-graph-integrity` |
| objective | inspect and report capsule-graph integrity; read-only |
| selected employee | `chief_architect` (1 of 10 eligible by capability match) |
| reasoning class | C (`small_reasoning`, rule `small_reasoning_floor`) |
| executor hint | `claude_code` |
| packet fingerprint | `f6e79a8c0652c37b` |
| authority fingerprint | `6764d89c319aac3f` |
| context fingerprint | `e2298854eed422da` |
| outcome | **accepted**, attempt 1, no retries |
| required test | `pytest tests/test_company_os_capsules.py -q` → 66 passed |
| working tree after | clean — the read-only constraint held |

**Findings the task produced** — independently corroborated by the dashboard's
own `system` section, which reads the same graph by a different path: 17
capsules; dependency graph acyclic (`find_cycles` returned empty); every
capsule reachable from the single root `company-os-control-plane`;
`CapsuleIndex.integrity()` reports no problems. Two capsules sit at the
`max_list_items = 8` dependency cap — `company-os-control-plane` **and**
`company-ceo-dashboard`. The next subsystem that must be reached from either
has to displace an existing dependency rather than add one.

## 4. Resource baseline

**Measurement source.** This execution environment *does* expose exact
provider-reported token counts: the Claude Code session transcript records the
Anthropic API `usage` block for every response. These are provider-reported
figures, not estimates. No number below is a character or word count relabelled
as a token.

> **Instrument note, because it would have doubled every number.** One API
> response is written to the transcript as several rows — one per content block
> (text, thinking, tool_use) — and each row repeats the *same* usage block.
> Summing rows over-counts by roughly 2×. Every figure below is deduplicated by
> `message.id`, the API response identity: 86 transcript assistant rows reduce
> to 35 distinct API responses in the measured prefix.

### A. The Company OS task that was dogfooded

Recorded on the real `ResourceUsageRecord`, fingerprint `ced38a43246112ed`.

| field | value | status |
|---|---:|---|
| usage unit | `token` | measured |
| input tokens (total) | 868,920 | measured — provider-reported |
| ├ fresh input | 14 | measured |
| ├ cache-creation input | 8,240 | measured |
| └ cache-read input | 860,666 | measured |
| output tokens | 3,166 | measured |
| └ of which reasoning/thinking | 511 | measured |
| **total tokens** | **872,086** | measured |
| tool calls | 7 | measured |
| duration | 49.6 s | measured |
| passes | 1 | measured |
| retries | 0 | measured |
| context expansions | 0 (0 required) | measured |
| expansion chars | 0 | measured |
| initial context refs | 9 (3 explicit, 6 capsule-derived) | measured |
| expanded context refs | 0 | measured |
| context precision | 0.333 (3 of 9 refs reported used) | measured |
| subagents used | 0 | measured |
| outcome | accepted | measured |
| reasoning class | C | measured |
| executor | `claude_code` | measured (hint) |
| model | `claude-opus-5` | measured |
| monetary cost | — | **unknown** (see §5) |

Two caveats a reader must carry:

*The input figure is dominated by cache reads.* 860,666 of 868,920 input tokens
were re-reads of an already-cached conversation prefix, because the task ran
inside a longer acceptance session rather than in a fresh one. A cold,
dedicated session for this task would read a far smaller prefix. **This is a
measurement of this run, not an estimate of the task's intrinsic cost**, and it
must not be multiplied by runs/day without accounting for that.

*The window boundary is a judgment, and it is stated rather than hidden.* "The
task" is the seven API responses between the packet being written and the
receipt being authored. Preparation (planning, packet construction) and
ingestion (receipt authoring) sit outside it and fall into session overhead
below.

### B. This coding-agent acceptance session

Measured over the session prefix up to the writing of this report, from the
same deduplicated provider-reported source.

| field | value |
|---|---:|
| input tokens (total) | 9,660,313 |
| ├ fresh input | 172 |
| ├ cache-creation input | 121,058 |
| └ cache-read input | 9,539,083 |
| output tokens | 38,528 |
| └ of which reasoning/thinking | 9,302 |
| **total tokens** | **9,698,841** |
| API responses | 86 |
| tool calls | 86 |
| duration | 1,213 s (~20 min) |
| model | `claude-opus-5` |
| source of measurement | Claude Code session transcript, Anthropic API `usage` block, deduplicated by `message.id` |

The session figure is a prefix, not a final total: it cannot include the tokens
spent writing, committing and reporting after the measurement was taken. Exact
final-message accounting is **unavailable** by construction — a session cannot
observe its own last response.

`cached_tokens` is reported split into cache-creation and cache-read rather
than as one number, because they are different quantities with different
costs.

The ratio worth noting for the CEO: the acceptance *session* cost about 11×
the task it was accepting. Verification, not execution, is where the resource
went in this cycle.

## 5. Finance — pricing completeness

**financial_cost: UNKNOWN. Reason: no explicit pricing evidence supplied.**

No `RateCard` exists in the repository, in the acceptance inputs, or anywhere
on this machine. None was fetched and none was hardcoded, as instructed.

The usage-cost bridge was still exercised end to end against the real
`ResourceUsageRecord` with an empty rate card, which is the documented correct
behaviour — a run over real usage with no rates prices nothing and says so:

```
usage_records_inspected : 1
attributions            : 3
priced                  : 0
unpriced                : 3
completeness            : unpriced
cost_per_accepted       : amount = null
missing                 : no rate for anthropic per token effective 2026-09-17
                          no rate for anthropic per request effective 2026-09-17
by_executor             : claude_code — 1 sample, 1 accepted, 3 unpriced
by_reasoning_class      : C — 1 sample, 1 accepted, 3 unpriced
```

| question | answer |
|---|---|
| applicable RateCard | none |
| accepted attempt known cost | unknown (unpriced) |
| rejected attempt known cost | no rejected attempts in this history |
| retry-bearing cost | 0 retry-bearing attempts |
| total known cost | unknown — **not zero** |
| cost per accepted deliverable | unknown; 1 accepted deliverable, no numerator |
| unpriced dimensions | token input, token output, per-request |

**Subscription vs API.** The executor ran under a Claude Code plan, not metered
per-token API billing. Token consumption is therefore a genuine resource
measurement, but the marginal monetary API cost is not applicable and has
deliberately not been synthesised. Converting these counts into currency
requires an explicit internal accounting rate card the CEO supplies; until
then, cost stays unknown, and unknown is not zero.

## 6. YouTube Studio ingestion

**Real export available: no.**

Only explicit project-provided locations were searched — the repository, the
acceptance input directory, and the project `exports/` tree. No personal
directories were searched broadly, no competitor analytics were used, no
scraping, no YouTube API.

No genuine own-channel Studio CSV was found, so `studio-inspect` and the
dry-run import were not run against fabricated data. The ingestion path is
present and its suite is green (`tests/test_company_youtube_studio_ingestion.py`
is part of the 1370), but it is **unexercised on real data in this
acceptance**.

Consequently: 0 observations imported, 0 video→deliverable mappings created, 0
unresolved mappings, and the Analytics section of the snapshot is honestly
`missing` rather than populated. No private analytics data was produced, and
none was committed.

The financial-column boundary (estimated revenue / RPM / CPM routed to Finance,
never turned into Analytics money records) was therefore not exercised on real
data either; it remains covered only by its tests. Finance was not modified in
this run.

## 7. CEO snapshot

Built over the acceptance state directory, read-only.

| | |
|---|---|
| snapshot id | `company-state-d14405cf8d723894` |
| as of | 2026-09-17 |
| decision queue | 0 |
| attention items | 0 |
| unresolved integrity issues | 0 |

| section | availability |
|---|---|
| execution | available |
| system | available |
| workforce | available |
| analytics | missing (`analytics:no_records`) |
| finance | missing (`finance:no_records`) |
| organization | missing (`organization:no_records`) |
| research | missing (`research:no_records`) |

Missing sections stayed missing. Nothing was fabricated to populate them.

**Execution dimensions:** 1 completed task, 1 accepted usage record, 0 rejected
attempts, 0 retries, 0 context expansions, 0 pending receipts,
`no_subagent_invariant: true`, `resource_monetary_cost: null`,
`context_precision: 0.333`.

**System dimensions:** 17 capsules, 0 integrity issues, 0 stale capsules,
`control_plane_direct_dependencies: 8`, `no_subagent_invariant: true`.

**Workforce dimensions**, read from the canonical `company/org_registry.yaml`,
which is a workforce source even with no derived records: 3 active, 7 dormant,
0 restricted, 0 candidate, 0 shadow, 0 probation employees; 0 capability gaps;
0 unresolved proposals; **14 critical single points of failure** — core
capabilities with zero or one *active* provider. Nobody was hired, activated or
otherwise changed during acceptance.

There is no graphical dashboard and none was built. The CEO Dashboard is JSON +
a compact text brief + the CLI; the brief was printed to the terminal.

## 8. Research / workforce / organization

| subsystem | state |
|---|---|
| research | no persisted records exist; section missing. No batches, sources, opportunities or dossiers were fabricated. |
| workforce | genuine configured state loaded from `org_registry.yaml` and `capability_registry.json`. The employment/shadow/gap/proposal record stores are empty. No hiring or activation performed. |
| organization | no persisted findings, recommendations or change proposals; section missing. Nothing fabricated. No organizational change self-approved — none existed to approve. |

## 9. Unknown / missing evidence

1. **Monetary cost** — no RateCard. Every cost dimension unpriced.
2. **Real YouTube Studio export** — not supplied; Analytics unexercised on real data.
3. **Research state** — never persisted by any prior session.
4. **Organization state** — never persisted by any prior session.
5. **Finance records** — none; cost, revenue and contribution all unknown.
6. **CEO decision queue** — empty, so `executive.decision_queue_preserves_source_refs` stays unknown.
7. **Workforce role records** — none, so `workforce.capability_gaps_visible` stays unknown.
8. **This session's final-message tokens** — unobservable from inside the session.

## 10. Privacy and production

Committed: this report only. Not committed: the acceptance state directory, the
snapshot JSON, the CEO brief, the gate JSON reports, the task and receipt
inputs, and the session transcript. No raw Studio export existed to leak. No
private analytics values, no financial evidence, no credentials, no API keys
and no personal information appear in this document. Every figure here is an
aggregate Company OS operating measurement.

Production modifications: **none**. No file under `race/`, `race2/`, `sloped/`,
`marble3d/`, `engine/`, `modes/`, `powers/`, `entities/`, `godot/` or
`production/` was touched. Nothing was published, rendered or merged.

## 11. Acceptance status

**ACCEPTED_WITH_MISSING_EVIDENCE.**

Every required technical check passes (34/34, 0 blockers, READY) and the
intended real-evidence paths that *had* inputs were genuinely exercised end to
end: real execution → real ResourceUsageRecord → real Finance attribution →
real CEO snapshot → gate against populated state.

It is not plain ACCEPTED because three optional real inputs were unavailable
rather than demonstrated: no RateCard, so money is unknown; no Studio export,
so the Analytics ingestion path is unexercised on real data; and no prior
research or organization state to load. Those are absences of input, not
failures of the system — which is why this is not BLOCKED.

## 12. Per-run forecast input

The measured baseline for later forecasting, stated with its caveat attached:

```
one accepted read-only class-C Company OS task
  = 872,086 total tokens measured  (868,920 in / 3,166 out)
  = 7 tool calls, 49.6 s, 1 pass, 0 retries, 0 expansions
  = 1 accepted deliverable
  = unknown money
```

**This figure must not be multiplied by runs/day as it stands.** 98.6% of its
input was cache re-read of a long shared session prefix. A cold single-task
session would consume materially less; a longer session would consume more. An
honest per-run forecast input needs one more measurement — the same task in a
dedicated session — which this run did not perform and did not estimate.

No demand forecast is made here, and no global efficiency score was computed.

## 13. Unresolved risks

1. **The capsule dependency graph is full in two places.**
   `company-os-control-plane` and `company-ceo-dashboard` are both at 8/8. The
   next subsystem must displace a dependency rather than add one, and the 7
   unowned modules above cannot be absorbed without confronting this.
2. **The per-run token figure is cache-inflated** and will be misread as
   intrinsic cost unless the caveat travels with it.
3. **Cost is structurally unknown**, not merely unmeasured. Until an internal
   accounting rate card exists, no cost-per-deliverable exists, and partial
   known cost must never be presented as full cost.
4. **14 core capabilities have one or zero active providers.** Real workforce
   evidence, surfaced by the first real snapshot, and worth a CEO decision.
5. **The Analytics → Finance revenue boundary is untested on real data** and
   will first be exercised under time pressure when a real export arrives.

## 14. Recommended next step

Supply one genuine own-channel YouTube Studio export into an explicit
acceptance input directory and re-run this acceptance with it. That single
input exercises the one remaining major integrated path (Studio → mapping →
observations → Analytics → snapshot), converts the Analytics section from
missing to available, and tests the revenue-column boundary before it matters.

Supplying an internal accounting RateCard at the same time would convert every
"unknown money" line in this report into a real number without changing any
code.
