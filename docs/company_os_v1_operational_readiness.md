# Company OS V1 — Operational Readiness Review

Branch: `company-os-v1-operational-readiness`, base `company-os-v1-bootstrap`
@ `5fbaa0cc7cff10c20119433ef8aca32b37fc04cd` (local worktree HEAD matched
`origin/company-os-v1-bootstrap` byte-for-byte before this document was
added — verified below). Worktree: `../wt-company-os-op-readiness`, per
[[parallel-agents-share-one-clone]] — the primary tree was mid-edit on
`v21-visual-contrast` and was not touched.

**Documentation only.** No runtime code was changed, no config was changed,
no branch ref was moved, no Company OS execution was run, and no subagent
performed any part of this review. This is a review of the evidence the
canonical branch already carries, not a new benchmark.

---

## 1. Verify the canonical baseline

`origin/company-os-v1-bootstrap` = `5fbaa0cc7cff10c20119433ef8aca32b37fc04cd`
— confirmed by direct `git rev-parse` against `origin`, matching the SHA
this milestone specified exactly. (The *local* `company-os-v1-bootstrap` ref
in the primary clone was stale at `01a1638`, behind but a fast-forward
ancestor; that is a local bookkeeping lag, not a divergence — `git
merge-base --is-ancestor 01a1638 5fbaa0c` is true.)

Every required item was checked against the tree at `5fbaa0c`, not assumed:

| Item | Present | Where |
|---|---|---|
| consumer resource mode | yes | `company/efficiency/profile.py` — `consumer`/`expanded` profiles; `docs/company_os_consumer_resource_mode.md` |
| corrected model routing | yes | `company.engineering.intake.derive_routing`; `docs/company_os_consumer_resource_mode.md` §3 |
| one automatic developer attempt | yes | consumer profile `automatic developer attempts: 1`; enforced at the job-state transition, not just configured |
| one reviewer pass | yes | consumer profile `reviewer passes: 1`, `auto-continue after changes_required: no` |
| no automatic retry after exhausted attempts | yes | `decision_required` on exhaustion; `max_developer_attempts` above the profile's is refused at construction |
| repository AST map | yes | `tools/engineering_runner/repo_map.py` |
| stream-json exploration telemetry | yes | `tools/engineering_runner/exploration_telemetry.py`, `exploration_report.py` — V1 found `--print --output-format json` cannot expose it; V2 found `--verbose stream-json` can, and wired it |
| symbol line spans | yes | `repo_map.py`: `ModuleMap.symbols` carries qualified name, kind, start/end line |
| reverse production dependencies | yes | `repo_map.py`: `RepoMap.production_dependents` |
| ExecutionContextBundle | yes | `tools/engineering_runner/execution_context.py` — ranked files, symbols+spans, dependents, tests, entry points, bounded excerpts |
| 6,000-character execution-context ceiling | yes | `MAX_BUNDLE_CHARS = 6000`, hard-truncated, chosen before the V2 matched job |
| acceptance-criteria test anchors | yes | `TestPatternAnchor` in `execution_context.py`; V3B matched job used it live |
| V3A routing precision fix | yes | referenced as V3B's baseline precondition (`docs/company_os_read_efficiency_v3b.md` §Preconditions) |
| external engineering runner hardening | yes | `docs/company_os_v1_external_runner_hardening.md` — 4 fixes, all measured |
| corrected usage telemetry | yes | `normalise_claude_usage`; disagreement marks `turns` unreliable rather than silently trusting a final-segment value |
| checkpoint/fresh-session mechanism | yes | `checkpoint.json` per run directory; excludes the transcript deliberately; continuation needs operator/CEO authorization |
| integration gate | yes | `company/integration/` — 34 required + 4 advisory checks, no score, `unknown` blocks |
| CEO approval boundary | yes | `authorizes_production_integration` and `authorizes_merge` are fields that are always `False`, and a report/result constructed with either `True` is refused |
| no-subagents rule | yes | traced end to end, `org_registry` → `permissions.bootstrap_defaults` → employee contract → `ExecutionPolicy` → packet → receipt → usage record, proven by `test_the_no_subagent_rule_holds_at_every_link` |
| no auto merge | yes | `Workspace` has no merge/rebase/tag/force-push method — asserted by a test reading the string constants |
| no deploy | yes | the runner's only outward call is `push`, one branch, one remote |
| no publish | yes | `production.no_publishing_capability` is required; Company OS may import no `subprocess`/`multiprocessing`/`pty` and call no `os.system`/`fork`/`exec*`/`spawn*` |

Nothing here was redesigned. Where a claim needed the source read rather
than trusted, the file is named above rather than the doc that describes it.

---

## 2. The actual evidence line

### Same-task comparisons (identical objective, rerun at a later baseline)

**`attempts-remaining`** — the objective run three times on the historical
BEFORE/AFTER-V2 lineage, then once more under the consumer profile:

| | BEFORE (`01a1638`) | AFTER-V2 (`5d73557`) | Consumer Mode V1 |
|---|---:|---:|---:|
| model | opus | opus | **sonnet** |
| authorized attempts | 3 | 3 | **1** |
| developer cost | $1.2719 | $1.7408 | $1.6406 |
| job cost (dev + reviewer) | $1.6317 | $2.0784 | $1.9362 |
| developer turns | 29 | — | 39 |
| developer cache-read | 1,347,797† | 2,226,932 | **1,835,390** |
| reviewer verdict / gate | pass / ready | pass / ready | pass / ready |

† 1,347,797 is the BEFORE job's own cache-read, recovered later by the
Repository Exploration V1 audit of stored runner state — not restated in
Consumer Mode V1's own table, which reported job-level cache-read
(1,913,995) rather than developer-only. Both numbers are genuine; they
describe different aggregation levels of the same session. Source:
`docs/company_os_consumer_resource_mode.md` §2, §13; `docs/company_os_repository_exploration_efficiency.md` §1.

**Consumer Mode V1 was not a per-session cost win — the docs say so
themselves.** Against AFTER-V2 it cost 6.8% less; against the original
BEFORE it cost 18.7% *more*. The cheaper model did more turns and more
output tokens on the same task, not the same work more cheaply. The
durable change is structural: **3 authorized attempts → 1**, a live
per-session spend ceiling that did not exist before in any form, and
telemetry that no longer silently drops 100,065 cache-creation units.

**`blocked_attempts` counter, V2 → V3B** — the one genuinely *identical*
same-task rerun in the whole lineage (`docs/company_os_read_efficiency_v3b.md`
§"Exact task match" confirms verbatim objective, acceptance criteria,
scope, risk and tier):

| | V2 | V3B |
|---|---:|---:|
| targeted pre-edit test reads | 10 | **4** (−60%) |
| developer cache-read | 783,941 | **568,012** (−27.5%) |
| developer turns | 26 | 19 |
| developer cost | $0.804993 | $0.635691 |
| reviewer cache-read | 47,922 | 46,535 (flat) |
| reviewer / gate | pass / ready | pass / ready |

### Similar-task comparisons (same tier/risk/shape, different named objective)

Repository Exploration V1 and V2 did **not** rerun Consumer Mode V1's own
task; each used a different, independently-classified routine objective of
the same shape (`docs/company_os_repository_exploration_efficiency.md`
§10: "Not the identical objective… classifies the same way"):

| | Consumer Mode V1 (`attempts-remaining`) | Repo Exploration V1 (`reviews-completed`) | Repo Exploration V2 (`blocked-count`) |
|---|---:|---:|---:|
| developer cache-read | 1,835,390 | **990,324** (−46.0% vs. left) | **783,941** (−20.84% vs. left) |
| developer turns | 39 | 27 | 26 |
| developer cost | $1.640637 | $1.083562 | $0.804993 |
| reviewer cache-read | — | 158,520 | 47,922 (−69.8% vs. V1) |
| reviewer cost | — | ~$0.374 | $0.213690 (−42.9% vs. V1) |
| total job cost | — | ~$1.457 | $1.018683 (−30.1% vs. V1) |

The reviewer-side reduction from V1 to V2 (cache-read −69.8%, turns −44.4%)
is the single largest efficiency gain in the whole lineage and is
documented, not asserted by inference — `ExecutionContextBundle` replaced
V1's free-text repo-map section and a near-duplicate whole-packet JSON dump
in both briefings.

### Historical observation (not a controlled comparison)

`tools/engineering_runner/exploration_report.py`, run once over all six
known runner-state roots on this machine: 21 stored sessions (10 developer,
11 reviewer), spanning several different objectives at several different
baselines. **avg developer cache-read: 2,584,057; max: 7,245,449.** This
number must not be read as "the cost of a routine job" — it mixes
unoptimized BEFORE-era sessions with post-hardening ones, and objectives of
different shapes. It is cited here only because it is the honest ceiling of
what has actually been observed on this machine, and it is materially
higher than every matched-job figure above.

**Do not average across these three categories.** A same-task number says
what changed for one fixed objective. A similar-task number says the same
class of objective got cheaper, with the caveat that n=1 per condition
(`docs/company_os_consumer_resource_mode.md` §13: "one sample per condition
proves less than it looks… nothing here establishes a per-session cost
saving") — the two historical BEFORE/AFTER-V2 runs on the *same* task and
*same* model differ by 37% themselves. The historical average is a
population statistic over unmatched work and answers a different question
than either.

---

## 3. Quality and failure-handling review

| Failure mode | Classification | Evidence |
|---|---|---|
| developer rejection (`changes_required`) | **PROVEN BY TEST, BOTH** | `eng-ai-resource-efficiency-v2` attempt 1 was genuinely rejected at review; attempts 2–3 on the operational branch rewrote most of the changed files in response — a real historical instance, under the (then 3-attempt) profile |
| reviewer `changes_required` with no attempts left | **PROVEN BY TEST** | moves the job to `decision_required`; `planning → developing` refused on an exhausted work order. Not yet hit live under the 1-attempt consumer profile — every live consumer-mode job so far passed review on attempt 1 |
| reviewer `blocked` | **PROVEN BY TEST** | `job -> gate \| planning \| decision_required \| blocked` is a real lifecycle transition with tests; not observed live (no live job has been blocked) |
| exhausted developer attempts | **PROVEN BY TEST** | see above; `max_developer_attempts` above the profile ceiling is refused at construction, not just at runtime |
| failed required tests | **PROVEN BY TEST** | the gate's honest default for unsupplied/failing suite evidence is `BLOCKED`, deliberately — "a check that runs its own evidence can never be `unknown`" |
| integration-gate failure | **PROVEN BY TEST, BOTH** | the gate has genuinely reported `BLOCKED` on a real branch base (`runtime-validation-decouple`'s capsule cycle) and `READY` on multiple others — both outcomes are real, not synthetic-only |
| authority violation / path outside authorization | **PROVEN BY TEST** | `PathRules.violations`, `protected_drift`; every live dogfood job reports "N checks, 0 violations" — that proves the check runs on real data without false positives, not that it correctly blocks a real violation, since none has occurred live |
| protected-file modification | **PROVEN BY TEST** | byte-digest based (`digest_paths`/`protected_drift`); no live job has touched a protected file, by design of every work order's scope so far |
| provider/session failure (crash, not budget-stop) | **NOT PROVEN live; PROVEN BY TEST** | the lifecycle is restart-safe by design (`developing -> (a run died here) resume`), and lease/heartbeat staleness was measured under 20×8 concurrent threads and real separate processes — but no actual live CEO job has crashed mid-session and been recovered |
| spend ceiling termination | **PROVEN BY TEST (real probe)** | `--max-budget-usd` was probed directly against the real Claude Code CLI (not assumed from docs): it stops the session, binds at turn boundaries (so a $0.0001 ceiling still overshot to $0.042), and reports `is_error:false` with an `error_*` subtype — a defect that would have hidden a cut-off session as a clean one, now read correctly |
| wall-clock termination | **PROVEN BY TEST** | "the runner terminates the child process" is implemented and asserted; no live job has run long enough to actually trigger it (largest recorded duration is 305.9 s against a 1800 s ceiling) |
| unreliable telemetry | **PROVEN BY TEST, BOTH** | found live (1 of 19 real sessions disagreed by 60× on turns before the fix); the fix now marks disagreement `unreliable` rather than silently preferring either value; the post-fix exploration audit found `sessions_with_unreliable_metrics: 0` across 21 further stored real sessions |
| interrupted runner | **PROVEN BY TEST** | directory-generation leases (`mkdir` on `lease-<N>`) measured at 20/20 correct grants across every starting state after the fix, versus up to 160/160 over-grants before it; six real separate processes also measured at exactly one `WON`. No live production interruption has actually occurred and been recovered from |
| checkpoint/resume | **PROVEN BY TEST, BOTH** | the checkpoint schema was verified against a real stored `checkpoint.json` from Consumer Mode V1's own matched job, not the code alone; an actual mid-job crash-and-resume during a live CEO job has not occurred |
| branch mismatch | **PROVEN BY TEST** | pre-check (packet branch/base agree with work order) and post-check (HEAD on authorized branch, base still an ancestor) both exist and are tested against real git repositories with real bare remotes |
| remote push verification failure | **PROVEN BY TEST, BOTH** | every live dogfood commit record states "pushed, remote SHA verified against the real refs" — the check runs for real on every real job, not only in the test harness |

**Nothing here is "proven" merely because the code exists.** Several rows
above are marked test-only specifically because the dogfood jobs run so far
were all low-complexity, narrowly-scoped, and none has actually failed,
crashed, been blocked, or run long/expensive enough to trip a ceiling. The
mechanisms are real and independently tested against synthetic adversarial
conditions (concurrent processes, malformed data, forged fields), but a
"the mechanism has never had to fire live" gap is real and is named as a
residual risk in §16 and as a stop condition in §15.

---

## 4. Authority review

| Action | Can a routine job do it? | Enforcement class |
|---|---|---|
| widen authorized paths | no | **technical impossibility** — `AuthorityEnvelope` is parsed from the brief; nothing writes one, and the change-scan reads `git diff`/`git status`, never the session's own account |
| increase its own developer attempts | no | **technical impossibility** — a work order requesting `max_developer_attempts` above the profile ceiling is refused at construction |
| select the strongest model without escalation | no | **technical impossibility** — only four named routes reach the strongest tier (reasoning class D+, HIGH/CRITICAL risk, an explicit `escalate_reasoning` field recorded as an authorization, or a documented prior standard-tier failure); none is silent |
| change protected governance | no | **technical impossibility** — protected files are digested by bytes before and after; any drift is a blocking violation, not a retry |
| approve itself | no | **technical impossibility** — `ControlPlane` has no `decide` method and the CLI has no `approve` verb; `authorizes_production_integration`/`authorizes_merge` are fields hard-pinned to `False`, and a record constructed with either `True` is refused |
| merge itself | no | **technical impossibility** — `Workspace` implements no merge, rebase, tag or force-push, asserted by a test reading the actual string constants |
| publish | no | **technical impossibility** — the runner's only outward network/git call is a single-branch `push`; `production.no_publishing_capability` is a required, AST-enforced gate check |
| deploy | no | **technical impossibility** — no deploy code path exists anywhere in Company OS or the runner |
| tag a release | no | **technical impossibility** — same `Workspace` constraint as merge |
| modify CEO decisions | no | **technical impossibility** — `CEODecision` requires `assert_named_person`; the dashboard projection carries no verb that can act on a work order |
| spawn subagents | no | **technical impossibility, doubly enforced** — `no_subagents=true` is threaded through org registry → permissions → contract → policy → packet → receipt and proven at every link by test; separately, `production.no_publishing_capability` forbids the process-spawning primitives a subagent would need regardless |

The one authority statement that is **policy/convention, not code**, is the
boundary between the developer session and the filesystem: the runner
enforces authorization on the **repository result** (the diff, the digest,
the branch, the ancestry), not on the **process**. A session is not
OS-sandboxed; nothing stops it, while running, from `cd`-ing outside its
worktree, though anything it changes there would sit outside the diff the
authority check reads and would simply not be part of the accepted result.
This is documented and named explicitly as the acceptance review's V2 item,
not hidden.

---

## 5. Resource viability

**SUPPORTED for the eligible routine category (§6), with one dimension
that stays structurally uncapped.**

The consumer profile's ceilings are real and were tested against the real
Claude Code CLI, not merely configured: wall clock (1800 s, enforced by
process termination), session cost ($3.00, enforced by `--max-budget-usd`
at turn granularity, when the backend accepts the flag), developer attempts
(1, enforced by the job state machine), context references (8, enforced at
packet construction), and runner stages (4, enforced by the runner
stopping and checkpointing).

**What remains variable, named plainly:** in-session repository exploration
— the developer's own reads, greps and re-reads before it edits anything —
has no dedicated ceiling. `docs/company_os_consumer_resource_mode.md` §5
states this directly: "no packet ceiling reaches it." It is not, however,
truly unbounded: it is transitively capped by the wall-clock and cost
ceilings above, since a session that explores too much simply burns time
and dollars against those two enforced limits rather than escaping
supervision. The measured range across every matched job to date
(568,012–1,913,995 developer cache-read units, $0.64–$1.94 job cost) sits
comfortably inside the $3.00 / 1800 s envelope; the 2,584,057-unit
historical average across all stored sessions (§2) is the number to watch,
since it implies some sessions have run closer to the ceiling than any
single matched job shows.

**Scope of this conclusion: bounded routine engineering work only.** Not
every engineering task fits inside a consumer subscription, and no document
in the canonical lineage claims one does — `docs/company_os_consumer_resource_mode.md`
§12 states this as a design non-goal, not a limitation discovered late.

---

## 6. Task eligibility policy

A routine-autonomous job should require all of: LOW/MEDIUM risk,
reversible, bounded authorized paths, acceptance criteria available,
required tests available, no CEO-reserved action, no credential handling,
no explicit specialist domain, no explicit escalation, no architecture
rewrite, no security-sensitive redesign, no governance-policy change, no
concurrency-critical redesign, no migration/schema/protocol breaking
change, STANDARD tier classification.

**Matches existing enforcement, with one named gap:**

| Criterion | Enforced today | How |
|---|---|---|
| LOW/MEDIUM risk | yes | `risk` field on the request, read by the classifier; HIGH/CRITICAL routes to specialist depth automatically |
| reversible | yes | `reversible` field; an irreversible request raises the reasoning-class ceiling to E, which `plan_task` refuses rather than silently downgrades |
| bounded authorized paths | yes | `PathScope`, forbidden-wins-over-allowed, empty allow-list allows nothing |
| acceptance criteria / required tests available | yes | derived deterministically from the owning capsule at intake; a work order without them is not constructed |
| no CEO-reserved action | yes | `permissions.yaml`'s reserved-action list, screened at intake (`screen_reserved`) |
| no credential handling | yes | `screen_credentials` at intake; separately, an AST walk asserts no Company OS package reads `environ`/`getenv` |
| no specialist domain / no explicit escalation | yes | `derive_routing`; an explicit domain or an `escalate_reasoning` flag routes away from routine |
| no architecture rewrite / security-sensitive / governance-policy / concurrency-critical | **partially** | `SPECIALIST_TRIGGERS` names *kinds of work* — security, governance, architecture, concurrency — matched against the objective text, deliberately not a table of sensitive directories |
| no migration/schema/protocol breaking change | **not separately named** | no `SPECIALIST_TRIGGERS` category was found for this specifically; such a change might trip the "architecture" trigger depending on wording, but this was not verified against a real or synthetic example and should not be assumed covered |
| STANDARD tier classification | yes | reasoning class C or below, per the classifier |

**This list would require one piece of new work, not a new architecture:**
a verification (and, if the gap is real, a trigger phrase or dedicated
check) that a schema, storage-format or wire-protocol breaking change is
reliably classified out of routine. Every other criterion is already
enforced by code that has been read directly for this review, not inferred
from a document's description of itself.

---

## 7. What "autonomous" would actually mean

The proposed ROUTINE AUTONOMOUS ENGINEERING mode — accept an eligible
request, classify, construct context, run one developer session, run
required tests, run one reviewer, run the gate, produce a decision packet,
stop before merge/deploy/publish — **is already the exact shape of the
external engineering runner**, and it has already executed this shape live,
repeatedly.

There is an apparent contradiction between two documents in the lineage
worth resolving explicitly, since a shallow read would miss it.
`docs/company_os_v1_engineering_execution.md` §8-9 states plainly that
"this is not autonomous" and lists the developer session, the review
session, running pytest, and running the gate as steps that "still need a
human." That document is accurate **for the phase it describes** —
`company/engineering` itself holds no process-spawn authority, by the same
rule (`production.no_publishing_capability`) that keeps Company OS honest.
But `tools/engineering_runner` is a **separate program, outside
`company/`**, built in the next phase specifically to hold the
process-spawn authority Company OS structurally may not: it launches the
developer session, launches the reviewer session, and its own lifecycle
table runs "11 suites, then `company.integration check`" as one of its own
stages. The multiple real jobs recorded in §2 (`attempts-remaining-consumer`,
`blocked-attempts-v3b`, `governance-drift-check`, `attempt-ledger`,
`scope-usage`, `stage-timing`, `reviews-completed`, `blocked-count`) all ran
this way: a human started the `watch` process once and submitted one
`CEORequest` per piece of work; everything from classification through the
gate report ran without further human action, and every one of them
stopped at `ready_for_approval` or a CEO-only state, never merged.

**So the current implementation already enforces this exact model** for
the eligible category in §6. The gap between what exists and the proposed
mode's prohibitions (invent its own work, auto-approve, merge, deploy,
publish, retry indefinitely, escalate silently, widen authority, chain a
new work order from a result) is not a gap at all — every one of those is
independently blocked by a mechanism named in §4, not by the runner's
own restraint.

---

## 8. Branch / source-control safety

Checked directly against the GitHub API (public repository, unauthenticated
read):

```
GET /repos/mgi25/Simulation-Factory/branches/company-os-v1-bootstrap
  "protected": false

GET /repos/mgi25/Simulation-Factory/branches/main
  "protected": false

GET /repos/mgi25/Simulation-Factory/rulesets
  []
```

**Canonical GitHub branch protected: no.** Neither `company-os-v1-bootstrap`
nor `main` carries any branch-protection rule or ruleset at the hosting
level. This matches the milestone's own stated external observation.

**A. Company OS's own execution boundary** already prevents it from
pushing to, merging into, or otherwise touching the canonical branch
outside its own authorized task branch — this is the §4 authority review,
and it holds regardless of GitHub settings.

**B. A human or a leaked credential could still push directly** to
`company-os-v1-bootstrap` or `main`, bypassing the entire developer → test →
review → gate → CEO-decision chain, because nothing at the hosting layer
prevents it. This is real and independent of anything Company OS enforces.

**Branch protection before routine autonomous engineering (state C):
RECOMMENDED, not REQUIRED, and here is the actual reasoning rather than a
default caution.** State C does not change what Company OS or the runner
can do to the canonical branch — that boundary is identical between states
B and C (§4). What state C changes is throughput: more routine jobs run per
unit of operator attention than under B's per-job authorization. More
jobs means more pushed task branches, more receipts, more surface for an
*operator* mistake (a wrong `--branch`, a stale worktree, a credential in a
committed file) to reach somewhere it shouldn't — and an unprotected
canonical branch is where that mistake would land hardest, since nothing
at the hosting layer would stop a direct push to it even by accident.
Recommended, not required, because the increase in exposure is about
operator throughput, not about anything the runner itself gains the power
to do.

**Task branches (`eng-*`, `company-os-v1-*` feature branches) do not need
separate hosting-level protection.** Their integrity is enforced at the
git-content level by Company OS at runtime — base-commit ancestry, branch
identity, protected-digest re-checking (§4) — not by GitHub. Protecting
every task branch would add hosting-level friction without closing a gap
Company OS doesn't already close itself. Canonical and `main` are the two
branches where a direct push bypasses the loop entirely; task branches are
disposable checkpoints by design (§9-12 of `docs/company_os_v1_integration_audit.md`).

---

## 9. Security / credential boundary

| Check | Status | Evidence |
|---|---|---|
| credentials not placed into model prompts | yes | no Company OS or runner module reads `environ`/`getenv` except `redaction.py`, and that module reads names only in order to strip values |
| child environment strips nested-session markers | yes | fixed from a denylist (which leaked `BINANCE_API_KEY`, `BINANCE_API_SECRET`, `CLAUDE_CODE_MESSAGING_TOKEN` among 100 real variables) to a three-class allowlist; 34 of 100 real variables cross the boundary now, and a real authenticated Claude Code session was verified to complete a prompt with zero auth variables forwarded |
| redaction exists for captured output | yes | `CommandResult.stdout` is scrubbed on the way in for every command; `report.json` — the one channel that bypassed this — was found unredacted and fixed with the same `Redactor`, tested with synthetic credential-shaped sentinels in `summary` and `unresolved_risks` |
| credential-trigger intake checks remain active | yes | `screen_credentials` at intake, unchanged by this or any recent milestone |
| Company OS does not silently authorize credential-management tasks | yes | intake screens for reserved/credential work before a work order is even constructed; the classifier's specialist triggers separately catch security-shaped objectives |

**Known residual exposure, stated rather than invented:** the developer
session is not OS-sandboxed (§4's authority caveat) — a credential *could*
theoretically be read by a session that chose to read outside the allowed
environment's forwarded variables or outside the repository, and nothing
would stop that while it happened. The mitigation is the allowlist itself
(the credential is simply not present in the child process to be read) plus
the repository-result-level authority check catching any resulting file
change. This is a review, not a penetration test, and no attack beyond what
the architecture already documents was attempted or is claimed to exist.

---

## 10. Observability

| Question | Answer | Basis |
|---|---|---|
| what work order ran | YES | `EngineeringWorkOrder`, fingerprinted, immutable once authorized |
| what model tier was chosen, and why | YES | `derive_routing` records the reasoning class and which of the four escalation routes (if any) applied |
| what context was supplied | YES | packet content is reference-only and sized (e.g., 1,179 chars pointing at 89,953 chars of source — a measured 26× ratio, not asserted) |
| what files changed | YES | read from `git diff --name-status` + `git status --porcelain`, never from the session's self-report |
| what tests ran | YES | per-suite results with names and counts, recorded in the receipt and the gate's suite evidence |
| what the reviewer decided | YES | `ReviewerAttestation`, adjudicated as `worst_of(attested, deterministic)` — a reviewer PASS cannot rescue a failed deterministic check |
| what the gate decided | YES | full `GateCheck` per condition — pass/fail/unknown, never a hidden aggregate |
| how much the session cost | YES, with a named caveat | session-total cost, read from `modelUsage` summed across models, cross-checked against `total_cost_usd`; disagreement is recorded, not hidden |
| cache-read/cache-creation usage | YES | both captured separately since the telemetry fix; previously cache-creation was invisible and silently read as zero |
| model turns where reliable | PARTIAL | reliable when segments agree; explicitly marked `unreliable` rather than reported when they don't — `check_budget` is wired to skip an unreliable turn count rather than trust it |
| file-read/search telemetry | PARTIAL | structurally unavailable from `--print --output-format json` (every session before the V2 fix); available via `--verbose stream-json`, wired going forward but not retroactive to older stored sessions |
| whether resource ceilings were exceeded | YES | wall-clock and attempt-count ceilings are enforced with a visible refusal; cost ceiling stop is visible via the `error_*` subtype fix (previously would have read as a clean completion) |
| whether any metric was unreliable | YES | `unreliable_metrics` is a named field on the record, not an absence |
| why the job stopped | YES | every terminal state (`ready_for_approval`, `decision_required`, `blocked`) carries the reason, and a `checkpoint.json` carries the same for a run that stopped mid-way |

No gap here is material enough to block operating within the eligible
category (§6) — the two PARTIAL rows are both cases where the system
correctly reports "I don't know" rather than reports a wrong number
silently, which is the property the design set out to guarantee.

---

## 11. Canonical branch and `main`

This review assesses operational readiness on `company-os-v1-bootstrap`
only. Nothing here evaluates, recommends, or moves toward merging Company
OS into `main`. `docs/company_os_v1_integration_audit.md` §15 already named
this as a separate, CEO-reserved, `permissions.yaml`-gated decision, and
this review changes nothing about that separation. Company OS being ready
to operate from its canonical branch and Company OS belonging on
production/simulation `main` remain two different decisions, and only the
first is in scope here.

---

## 12. No more efficiency tool experiments

None recommended. Graphify, Serena, RTK, Ponytail, ast-grep, embeddings and
vector databases are not installed in this repository (confirmed in
`docs/company_os_read_efficiency_v3b.md`'s own "External tools" section:
all five listed as not installed, most recently checked at V3B), and the
evidence line in §2 does not point at a bottleneck any of them would
address. V3B's own conclusion stands: "the developer's now-dominant cost is
genuinely implementation work… any further efficiency gain here would have
to come from a different dimension… not from more repository intelligence."
This review adds nothing to that.

---

## 13. No new live dogfood run

None was run for this review. Every number in §2–§10 comes from documents
already committed to the canonical lineage. Where evidence was insufficient
to answer a question precisely — the migration/schema-trigger gap in §6,
the never-yet-triggered ceilings in §3, in-session exploration's transitive
(not dedicated) bound in §5 — that insufficiency is stated directly rather
than papered over with a new benchmark.

---

## 14. Readiness decision

**Recommended state: C — ROUTINE AUTONOMOUS ENGINEERING WITH CEO APPROVAL
GATE, scoped exactly to the eligibility list in §6.**

This is a step beyond where the immediately preceding milestone
(`docs/company_os_v1_integration_audit.md`, same canonical SHA, same day)
left the status — it recorded "CONTROLLED ROUTINE DOGFOOD… autonomous
engineering remains PAUSED." That document is not being second-guessed
lightly, so the reason for reaching a different conclusion here is stated
plainly: the integration audit was chartered as **read-only branch
archaeology** and said so of itself — it checked ancestry, not the
hardening, authority, and failure-handling evidence this review compiled.
Its one-line operating-status note carried the prior status forward because
finding no code defect in a branch-inventory task is not the same activity
as weighing whether to lift the pause; its own text says exactly that
("supplies no new reason to lift the pause… not READY FOR BROADER
OPERATION; that would need new evidence this audit did not produce"). This
review is the first one actually chartered to do that weighing, over
evidence that already exists in the tree: the runner-hardening pass's four
independently-verified fixes (§3, §9), the consumer profile's tested
ceilings (§5), the authority matrix's technical (not merely procedural)
enforcement (§4), and multiple real CEO-issued jobs that ran the full loop
to `ready_for_approval` without a single observed authority violation.

**Why not stay at B.** State B and state C carry an *identical* technical
boundary — nothing Company OS or the runner is permitted to do changes
between them (§4, §7). The only real difference is that B requires a human
to individually authorize each job before it starts, and C lets an eligible
job run once submitted. Given that boundary is unchanged, the case for
staying at B is a case for more supervision per job, not more safety per
job — and the evidence in §3 says the supervision has caught zero live
authority violations across every recorded job so far, against mechanisms
independently stress-tested (concurrent leases, forged receipt fields,
malformed SHAs) rather than merely asserted.

**Why not D.** Several rows in §3 are explicitly test-only, not
dogfood-proven: exhausted-attempt handling under the 1-attempt consumer
profile, a live crash-and-resume, a live triggered wall-clock or cost
ceiling, and a live blocked/rejected job under the current profile. None of
that supports extending beyond the routine/eligible category — specialist,
high-risk, architecture, security or governance work is explicitly out of
scope for C and stays there.

---

## 15. Stop conditions for state C

State C automatically falls back to CONTROLLED ROUTINE DOGFOOD (state B)
— and to PAUSED if the trigger indicates the technical boundary itself may
be compromised — on any of:

1. **Any authority violation actually occurs** — a receipt reporting a
   change outside `may_write`, a protected-digest drift, or a HEAD found
   off the authorized branch. Fall back to PAUSED; this contradicts a
   mechanism this review classified as a technical impossibility, and that
   claim must be re-examined before any further routine job runs.
2. **An automatic retry occurs when the consumer profile said none.** Fall
   back to PAUSED for the same reason as (1).
3. **The strongest tier is selected for a routine job without one of the
   four named routes (§4) being recorded on the work order.** Fall back to
   B and re-audit `derive_routing`.
4. **A routine job's developer cache-read or cost materially exceeds the
   measured historical range** (§2's matched-job range is 568,012–1,913,995
   cache-read units, $0.64–$1.94 job cost; the broader stored-session
   average is 2,584,057) **without a scope explanation on the work
   order.** This is the one dimension §5 named as transitively, not
   directly, bounded — treat a job that approaches the $3.00/1800 s
   ceiling as a live test of that transitive bound, not routine
   operation. Fall back to B.
5. **Telemetry is marked unreliable on a routine job.** Fall back to B
   until the specific disagreement is understood; do not average through it.
6. **Two consecutive routine jobs require manual recovery** (a checkpoint
   was needed, a lease had to be reclaimed, a receipt was rejected for a
   reason other than a clean scope refusal). Fall back to B.
7. **Reviewer and gate disagree in a way the current lifecycle states
   cannot represent** (i.e., neither `ready_for_approval`,
   `decision_required`, nor `blocked` describes the outcome). Fall back to
   PAUSED — this is a state-machine gap, not a routine failure.
8. **The canonical branch's ancestry diverges unexpectedly** (a force-push,
   a rewrite, or a commit on `company-os-v1-bootstrap` that this review's
   `git merge-base --is-ancestor` chain would not predict). Fall back to
   PAUSED immediately; §8 already names why this branch is exposed.
9. **Protected governance changes outside an authorized work order.** Fall
   back to PAUSED.
10. **GitHub branch protection is still absent 30 days after this review
    is accepted**, if it is accepted. Not an immediate trigger, but a
    standing condition — recommended in §8 and §16, and its continued
    absence should be revisited rather than forgotten once operation
    begins.

---

## 16. Branch protection recommendation

Recommendation only; nothing was changed.

- **Prevent force pushes** to `company-os-v1-bootstrap` and `main`.
- **Prevent deletion** of both.
- **Require a pull request, or an explicit operator-controlled update,**
  rather than an unreviewed direct push, for `company-os-v1-bootstrap` —
  consistent with how every accepted phase branch in the lineage has
  actually landed (a named merge commit, not a silent fast-forward from an
  arbitrary source).
- **Protect `main` with the same rules**, independently — it is currently
  also unprotected (§8), and is the eventual target of a future,
  separately-authorized integration decision (§11), which should not be
  able to be pre-empted by a direct push today.

---

## 17. Output

This document: `docs/company_os_v1_operational_readiness.md`, on branch
`company-os-v1-operational-readiness`, based on
`company-os-v1-bootstrap` @ `5fbaa0cc7cff10c20119433ef8aca32b37fc04cd`.
No other file in this branch differs from that base.

---

## FINAL REPORT

```
canonical branch: company-os-v1-bootstrap
canonical SHA: 5fbaa0cc7cff10c20119433ef8aca32b37fc04cd

evidence reviewed: docs/company_os_v1_bootstrap.md,
  docs/company_os_v1_branch_dag.md, docs/company_os_v1_integration_audit.md,
  docs/company_os_v1_acceptance_report.md,
  docs/company_os_v1_external_runner_hardening.md,
  docs/company_os_v1_external_engineering_runner.md,
  docs/company_os_v1_engineering_execution.md,
  docs/company_os_v1_session_execution.md,
  docs/company_os_v1_production_integration_gate.md,
  docs/company_os_consumer_resource_mode.md,
  docs/company_os_read_efficiency_v3a.md, docs/company_os_read_efficiency_v3b.md,
  docs/company_os_repository_exploration_efficiency.md,
  docs/company_os_repository_exploration_efficiency_v2.md,
  plus direct reads of tools/engineering_runner/repo_map.py,
  exploration_telemetry.py, execution_context.py, and a live,
  unauthenticated GitHub API check of both branches' protection status.

QUALITY

developer execution: one automatic attempt, standard tier reachable and
  observed live in every matched job; retry-on-rejection proven once,
  historically, under the earlier 3-attempt profile
reviewer: independent capability, worst_of(attested, deterministic)
  adjudication, cannot rescue a failed check
integration gate: 34 required + 4 advisory checks, unknown blocks, no score,
  observed both READY and BLOCKED live on real branch bases
authority enforcement: technical impossibility for every reserved action
  checked (§4); one named non-technical boundary (process-level sandboxing)
failure handling: mechanisms exist and are independently tested for every
  listed failure mode; several have not yet fired on a live job (§3)
checkpoint/resume: real artifact format verified against a genuine stored
  checkpoint; live mid-job crash recovery not yet observed

RESOURCE VIABILITY

routine consumer viability: SUPPORTED (scoped to bounded routine
  engineering work, §5)

latest same-task developer cache-read: 568,012 (V3B, vs. V2's 783,941,
  -27.5%)
latest same-task developer cost: $0.635691 (V3B, vs. V2's $0.804993)
latest same-task targeted pre-edit test reads: 4 (V3B, vs. V2's 10, -60%)

AUTHORITY

can widen paths: no (technical impossibility)
can self-approve: no (technical impossibility)
can merge: no (technical impossibility)
can deploy: no (technical impossibility)
can publish: no (technical impossibility)
can spawn subagents: no (technical impossibility, doubly enforced)
can silently escalate model: no — four named, recorded routes only

OBSERVABILITY

work order trace: YES
model routing trace: YES
context trace: YES
diff trace: YES (from git, never self-reported)
tests: YES
review: YES
gate: YES
cost: YES, with disagreement surfaced rather than hidden
cache usage: YES, cache-creation now visible (previously silently zero)
exploration telemetry: PARTIAL — available via stream-json going forward,
  structurally unavailable for sessions recorded before that mode was wired
unreliable-metric signaling: YES — a named field, not an absence

SOURCE CONTROL

canonical GitHub branch protected: no (verified live against the GitHub
  API on both company-os-v1-bootstrap and main; no rulesets either)

branch protection before State C: RECOMMENDED, not REQUIRED — reasoning in
  §8 (the technical boundary is identical between B and C; the exposure
  state C adds is operator throughput, not runner capability)

remaining material risks:

1. In-session repository exploration has no dedicated ceiling — only a
   transitive bound via wall-clock and cost ceilings, which every matched
   job so far has stayed well inside but the historical session average
   (2,584,057 cache-read) approaches more closely than any single matched
   job shows.
2. Several failure-handling mechanisms (exhausted-attempt fallback under
   the 1-attempt profile, live crash recovery, live ceiling trips, a live
   blocked/rejected job) are proven by test and by stress harness, not yet
   by an actual live occurrence.
3. The task-eligibility policy has no separately-named trigger for a
   migration/schema/protocol breaking change; it may or may not be caught
   by the existing "architecture" trigger, and this was not verified.

recommended operating state: C

reason: the technical enforcement boundary (§4) is identical between
  Controlled Routine Dogfood and Routine Autonomous Engineering — nothing
  Company OS or the runner is permitted to do changes between them. State
  B's extra per-job human authorization has caught zero live authority
  violations against mechanisms that were independently stress-tested, not
  merely asserted. The prior milestone's PAUSED-leaning note was written
  under a read-only-archaeology charter that did not weigh this evidence;
  this review does.

if C:
eligible task definition: LOW/MEDIUM risk, reversible, bounded authorized
  paths, acceptance criteria and required tests available, no CEO-reserved
  action, no credential handling, no specialist domain or escalation, no
  architecture/security/governance/concurrency-shaped objective, STANDARD
  tier — per §6, with the migration/schema gap named above
CEO approval remains required: yes

automatic merge: no
automatic deploy: no
automatic publish: no

fallback/stop conditions:

1. any live authority violation -> PAUSED
2. an automatic retry when the profile authorized none -> PAUSED
3. strongest tier selected without a named route recorded -> B
4. a routine job materially exceeds the measured resource range without a
   scope explanation -> B
5. telemetry marked unreliable on a routine job -> B
6. two consecutive routine jobs need manual recovery -> B
7. reviewer/gate disagreement the lifecycle cannot represent -> PAUSED
8. unexpected canonical branch ancestry divergence -> PAUSED
9. protected governance changes outside an authorized work order -> PAUSED
10. GitHub branch protection still absent 30 days after acceptance ->
    standing condition, revisit

main integration authorized: no

additional efficiency work required before operation: no — §2's evidence
  is within the consumer profile's tested ceilings, and §12 finds no
  unaddressed bottleneck a new tool would close

verdict:

COMPANY OS V1 OPERATIONAL READINESS:
READY WITH CONDITIONS
```
