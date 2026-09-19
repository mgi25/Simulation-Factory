# Company OS V1 — Canonical Integration Audit

Branch: `company-os-v1-integration-audit`, base
`company-os-v1-read-efficiency-v3b` @ `4acee87c5e6f250754b35d7b876eac948a0349f7`
(local == remote, verified before cutting). Worktree:
`../wt-integration-audit` (sibling of the main clone, per
[[parallel-agents-share-one-clone]] — the primary tree was mid-edit on
`v21-visual-contrast` and was not touched).

**Read-only archaeology.** No runtime code was changed. The only
verification run was the full deterministic `pytest` suite once, to check
the fingerprint (§14). No Company OS execution, no matched job, no reviewer
session, no live AI dogfood — per the milestone brief, §15.

Raw ancestry data backing every claim below:
`docs/validation/company_os_v1_integration_audit/branch_audit_results.txt`
(one line per branch: HEAD SHA, ancestor-of-V3B, ancestor-of-bootstrap,
merge-base, commits-ahead, diffstat — all from `git merge-base`,
`git merge-base --is-ancestor`, `git rev-list --count`, `git diff --stat`,
never from branch names or memory).

## 0. Pre-flight verification (done before cutting the branch)

* `origin/company-os-v1-read-efficiency-v3b` exists; local and remote HEAD
  agree at `4acee87`.
* `origin/company-os-v1-read-efficiency-v3a` (`ba851fa`) is an ancestor of
  V3B — `git merge-base --is-ancestor` true.
* V3B's own two commits (`9e6c604` implementation, `4acee87` matched-job
  record) are present in `git log v3a..v3b`.
* The V3B matched-job result is documented at `docs/company_os_read_efficiency_v3b.md`
  in the V3B tree itself (found via `git show v3b --stat`).
* Worktree created clean (`git worktree add ../wt-integration-audit -b
  company-os-v1-integration-audit company-os-v1-read-efficiency-v3b`);
  `git status` empty immediately after.
* V3B was not modified: the new branch only gains new `docs/` files (this
  report, the DAG, the raw audit data).

## 1–2. Branch inventory and the real DAG

37 `company-os-v1-*` branches + 12 related branches (`eng-ai-resource-efficiency-v2`,
`eng-ai-resource-efficiency-v2-operational`, and 10 further `eng-*` dogfood
branches — the complete list from `git branch -r`, not a guess) = **49
branches inspected**, all listed with SHA/date/ancestry in the raw data file.

The actual DAG, reconstructed from `git merge-base`/`--is-ancestor`/
`rev-list`, is in `docs/company_os_v1_branch_dag.md`. Headline: **this is one
history, not 37.** `company-os-v1-bootstrap` has been fast-forwarded to
`01a1638` (identical to `company-os-v1-external-runner-hardening`), and
`01a1638` is an ancestor of V3B. Every phase branch this audit checked is
`--is-ancestor`-true against that chain except the two naming traps in §3.

## 3. Classification

### ANCESTOR — 36 branches (already fully contained in V3B)

All of: `ai-efficiency`, `analytics-experiments`, `bootstrap`, `ceo-dashboard`,
`consumer-resource-mode`, `context-assembly`, `context-expansion`,
`core-runtime`, `dashboard-observation-identity-fix-reviewed`,
`dogfood-research-capsule`, `efficiency-harness`, `engineering-execution`,
`execution-transport`, `external-engineering-runner`,
`external-runner-hardening`, `finance-cost-dogfood`, `finance-foundation`,
`knowledge-capsules`, `org-intelligence`, `production-integration-gate`,
`read-efficiency-v3a`, `real-efficiency-telemetry`, `real-evidence-acceptance`,
`repository-exploration-efficiency`, `repository-exploration-efficiency-v2`,
`research-batches`, `research-ingestion`, `research-intelligence`,
`runtime-integration`, `runtime-validation-decouple`, `session-execution`,
`workforce-foundation`, `youtube-connectivity`,
`youtube-studio-ingestion-reviewed` (all `company-os-v1-*`), plus
`eng-ai-resource-efficiency-v2-operational`.

**Reason, uniformly:** `git merge-base --is-ancestor <branch> V3B` is true,
and `git rev-list --count <mergebase>..<branch>` is 0 — the branch HEAD *is*
a commit already on the V3B line (as a first-parent commit or as the second
parent of one of the 23 `Merge …` commits in §2b of the DAG doc). Nothing to
integrate; these names are checkpoints, not pending work.

### SUPERSEDED — 3 branches

* **`company-os-v1-dashboard-observation-identity-fix`** (`a9bd079`) —
  superseded by its own `-reviewed` sibling (`d899467`), which is the one
  actually merged (DAG §2b row 22). The plain branch is 2 commits *ahead*
  of `-reviewed` (`noop`, `Remove accidental review artifact`) with an
  otherwise byte-identical tree (`git diff --stat` empty). Do not integrate
  the plain branch; it adds nothing but two junk commits over what is
  already in.
* **`company-os-v1-youtube-studio-ingestion`** (`41f8d74`) — same trap, worse:
  superseded by `-reviewed` (`583e457`, DAG §2b row 20), 12 commits ahead
  (`temp`, `noop`, `x`, `cleanup accidental temporary file`, repeated),
  tree again byte-identical.
* **`eng-ai-resource-efficiency-v2`** (`5c1c035`) — superseded within its
  *own* work order. `git log -1` shows `Work-Order:
  wo-ceo-2026-09-18-ai-resource-efficiency-v2 … attempt 1`. The next two
  commits on the accepted line (`eng-ai-resource-efficiency-v2-operational`,
  `25fddf8`/`1a50f5e`/`5d73557`) are explicitly attempts 2–3 of the *same*
  work order after `changes_required` review feedback, and rewrite most of
  attempt 1's files wholesale: `git diff --stat` between the two shows
  `company/efficiency/audit.py`, `routing.py`, `tool_evaluation.py` deleted
  (−324/−186/−276 lines) and replaced by new `baseline.py` (+345),
  `budget.py` (+123), and a rewritten `strategy.py` (507 lines changed),
  1,485 insertions / 1,229 deletions across 12 files. Attempt 1's code
  never reached the accepted line; do not resurrect it.

### DOGFOOD_ARTIFACT — 10 branches (`eng-*`, none belong in product code)

Every one of these is a single- or few-commit branch that adds a small,
isolated counter/dataclass to `company/engineering/*`, used once as a
matched-job fixture and then abandoned by design. None of their production
files exist anywhere on the V3B line (checked directly: `git show
v3b:company/engineering/attempt_ledger.py` etc. all `fatal: … does not
exist`). Several are provably the *recorded* output of a validation job
already documented inside V3B's own tree — matched by commit SHA, not by
name:

| Branch | HEAD | Files touched | Matched to stored evidence |
|---|---|---|---|
| `eng-attempt-ledger` | `d681c5a` | `company/engineering/attempt_ledger.py` (+`__init__.py`, tests) | `docs/validation/company_os_external_engineering_runner/job1-attempt-ledger/.../receipt.json` — `commit_sha` field is this exact SHA |
| `eng-scope-usage` | `be5255d` | `company/engineering/result.py` (`ScopeUsage`) | `job2-scope-usage/.../receipt.json` — same SHA |
| `eng-stage-timing` | `ae703ff` | `company/engineering/lifecycle.py` (`StageTiming`) | `job3-stage-timing/.../receipt.json` — same SHA |
| `eng-governance-drift-check` | `d59a5d9` | `company/engineering/verify.py`, `__main__.py` | referenced by SHA in `docs/company_os_v1_engineering_execution.md` and `docs/validation/company_os_engineering_execution/03-receipt*.json` (work order `wo-governance-drift-check-3e66f7617527`) |
| `eng-attempts-remaining` | `9336146` | `result.py` (`attempts_remaining`) | named as the historical **BEFORE** case in `docs/company_os_consumer_resource_mode.md` |
| `eng-attempts-remaining-after` | `f618710` | `result.py`, tests | the **AFTER-V2** case in the same doc (cost comparison $2.078 vs $1.632) |
| `eng-attempts-remaining-consumer` | `8dde087` | `result.py`, tests | the **CONSUMER** case, `docs/company_os_consumer_resource_mode.md`: "branch `eng-attempts-remaining-consumer`, commit `8dde0876`. Reviewer PASS, gate READY" |
| `eng-blocked-attempts-consumer` | `6181e3c` | `lifecycle.py` (`blocked_attempts`) | the V2 case named in `docs/company_os_repository_exploration_efficiency_v2.md` |
| `eng-blocked-attempts-v3b` | `cc78d0e` | `lifecycle.py`, tests | V3B's own matched job, `docs/company_os_read_efficiency_v3b.md`: "`eng-blocked-attempts-v3b`) … gate says ready at `cc78d0efcdef`" |
| `eng-reviews-completed-repoexpl` | `cc152bf` | `store.py` (`reviewer_passes_completed`) | the V1 "`reviews-completed`" case named in the V2 doc's comparison table |

**Per §5 of the brief (A/B/C/D):** all ten are **category B** — matched
benchmark fixtures, not implementations intended for Company OS product
code. None have been independently reimplemented elsewhere (checked: none
of the eight distinct counters exist under `company/engineering/` on the
V3B line). **Category D applies: they stay outside the integration
baseline.** The counters themselves (`attempts_remaining`, `blocked_attempts`,
`scope_usage`, `stage_timing`, `attempt_ledger`, `reviewer_passes_completed`,
a governance-drift check) could become real product features some day, but
that is a fresh CEO decision to write and review as new work, not a
cherry-pick of a benchmark commit — several of these branches exist in
*multiple*, deliberately-divergent versions of the same feature (three
`attempts-remaining` variants, two `blocked-attempts` variants) specifically
because they were re-run at successive baselines to measure cost, and no
single one of them is "the" correct implementation to keep.

### PARALLEL_ACCEPTED / PARALLEL_REVIEW_REQUIRED / EXPERIMENTAL (non-superseded) / DOCUMENTATION-ONLY / UNKNOWN — 0 branches each

None found. This is the audit's second headline finding: there is currently
no parallel Company OS work sitting outside the accepted line waiting to be
integrated. The "branch fragmentation" problem named in the milestone
background is **evidence of history, not a backlog** — 34 of the 37
`company-os-v1-*` branches are literal ancestors-by-identity of V3B, 2 more
are byte-identical superseded duplicates of ancestors, and the "related
engineering" branches are all disposable dogfood fixtures, one of them
(`eng-ai-resource-efficiency-v2`) a rejected first attempt at a work order
whose accepted attempts are themselves on the line.

## 4–5. Unique code by subsystem / dogfood vs. product

Given §3's result, there is no PARALLEL_ACCEPTED or PARALLEL_REVIEW_REQUIRED
set to break down by subsystem — every subsystem named in the milestone
background (runtime, context, knowledge, workforce, research, finance,
analytics, dashboard, youtube, engineering, runner, efficiency, governance)
already has its accepted implementation on the V3B line, at the merge points
listed in `company_os_v1_branch_dag.md` §2b–2d. The only "unique code"
outside the line is the ten dogfood counters (§3) and the one rejected V2
attempt (§3), neither of which the brief permits treating as product code
without a fresh review.

## 6. Proposed canonical base

**`company-os-v1-read-efficiency-v3b` @ `4acee87` stays the proposed starting
point.** No other branch was found with a more complete accepted lineage —
every other branch checked is either already an ancestor of this commit or a
disposable artifact. It carries: the full phase-branch backbone (§2b),
runner hardening ([[external-runner-hardening-stop-condition]]), consumer
resource mode ([[consumer-resource-mode-stop-condition]]), two rounds of
repository-exploration efficiency, and its own STANDARD-tier matched-job
result (targeted pre-edit reads 4, developer cache-read 568,012, reviewer
PASS, gate READY, per the milestone background). It is the branch with the
fewest known open defects and the freshest telemetry.

## 7. Integration order

**None required for the 36 ANCESTOR / 3 SUPERSEDED branches** — there is
nothing to fast-forward, merge, or cherry-pick; they are already reachable
from V3B. The only branch-management action this audit recommends for the
*next* milestone is **advancing `company-os-v1-bootstrap` again** (as was
done once already, per [[company-os-canonical-baseline]]) so that name keeps
tracking the single accepted line — a fast-forward, zero conflict risk, no
code change.

No PARALLEL_ACCEPTED branch exists, so there is no multi-stage integration
plan to write for §7 of the brief. If the *next* milestone chooses to turn
any of the ten §3 dogfood counters into real product features, each is a
fresh single-file, low-conflict change against `company/engineering/`
(`result.py`, `lifecycle.py`, `store.py`, or a new module) — safe to author
new, not to cherry-pick from the dogfood commit, since the dogfood commit's
own review evidence was scoped to "does the runner work," not "is this the
right shape for the feature."

## 8. Duplicate/conflicting implementations

Found exactly two duplicate-implementation situations, both already
resolved on the accepted line:

* **AI Resource Efficiency V2**: `eng-ai-resource-efficiency-v2` (attempt 1)
  vs. `eng-ai-resource-efficiency-v2-operational` (attempts 2–3) — **conflicting**,
  resolved in favor of the operational one (§3).
* **Dashboard identity fix** and **YouTube Studio ingestion**, each vs. its
  own `-reviewed` sibling — **additive-but-junk**, resolved in favor of
  `-reviewed` (§3).

No other overlap was found among context-assembly/context-expansion,
runner-hardening/efficiency, dashboard-identity/later-dashboard-work, or the
three named "AI efficiency" generations — each of those pairs named in the
brief's §8 checklist turned out to be sequential (context-expansion is
built after context-assembly and merges separately; runner-hardening and the
efficiency lineage are sequential phases on the same line, not competing
implementations of one thing).

## 9. Acceptance evidence strength

* **STRONG**: `read-efficiency-v3b` (matched job + reviewer PASS + gate
  READY, documented), `external-runner-hardening` (independent acceptance
  review with 4 named fixes, verified), `consumer-resource-mode` (matched
  job + CEO decision recorded + gate READY), `repository-exploration-efficiency-v2`
  (matched job, reviewer PASS, gate READY), `read-efficiency-v3a` (same).
* **MODERATE**: the remaining phase branches merged in §2b (`core-runtime`
  through `real-evidence-acceptance`) — each has a milestone doc and tests
  in the tree, but this audit did not re-derive an independent gate/review
  artifact for every one of them individually; their evidence is inherited
  from being on the accepted, gated line, not separately re-verified here.
* **WEAK→then fixed**: `eng-ai-resource-efficiency-v2-operational` itself
  carried a **REQUEST CHANGES** verdict on its own AFTER-validation dogfood
  run (`ai-resource-efficiency-v2-after-validation`) at the time it was
  written — the four defects it found (STANDARD tier unreachable, strategy
  inert, context narrowing wrong, output reduction never runs) were the
  explicit fix list for `consumer-resource-mode`, which does carry STRONG
  evidence. Not converted to STRONG retroactively; recorded as what it was.
* **REJECTED**: `eng-ai-resource-efficiency-v2` attempt 1 (changes_required,
  superseded, §3).
* **N/A (benchmark, not a ship decision)**: all ten §3 dogfood branches.

## 10–11. Deterministic tooling / risk

All ancestry claims in this report came from `git merge-base`,
`--is-ancestor`, `rev-list --count`, and `diff --stat`/`--name-only` — no
commit was read by eye to establish ancestry. Consequently there is **no
HIGH-risk overlap to report**: risk classification only applies to
integration steps, and §7 found none needed. The one thing worth a human
read before any future work: the two `-reviewed` vs. plain-name pairs in §3
are a standing trap for anyone who greps branch names instead of checking
ancestry — worth a one-line note in team documentation, not a code fix.

## 12. Branch retention plan

* **KEEP — CANONICAL / ACTIVE**: `company-os-v1-read-efficiency-v3b`,
  `company-os-v1-bootstrap` (tracks the same commit), and this new
  `company-os-v1-integration-audit`.
* **KEEP — HISTORICAL EVIDENCE**: all 34 other ANCESTOR branches (§3) —
  each is a checkpoint with its own milestone doc; deleting them would not
  change any code but would remove convenient named anchors into the
  history. `eng-ai-resource-efficiency-v2-operational` likewise.
* **ARCHIVE CANDIDATE — SUPERSEDED**: `company-os-v1-dashboard-observation-identity-fix`,
  `company-os-v1-youtube-studio-ingestion`, `eng-ai-resource-efficiency-v2`.
* **ARCHIVE CANDIDATE — EXPERIMENTAL / DOGFOOD**: the ten `eng-*` branches
  in §3's table.
* **DO NOT TOUCH — UNCERTAIN**: none identified.

No branch was deleted, renamed, or archived by this milestone — inventory
only, per the brief.

## 13. Company OS operating status

Recommendation: **CONTROLLED ROUTINE DOGFOOD**, unchanged from before this
audit. This milestone found no code defect and no fragmentation requiring
integration work, so it supplies no new reason to lift the pause recorded in
[[consumer-resource-mode-stop-condition]] (live repository exploration still
dominates resource usage; no packet/profile ceiling reaches inside a
session). It also finds no reason to *tighten* the status — the "branch
fragmentation" concern that motivated this milestone turned out to already
be resolved. **Not** READY FOR BROADER OPERATION; that would need new
evidence this audit did not produce (it was archaeology, not a dogfood run).

## 14. Test fingerprint verification

Ran the full deterministic suite once, from the audit worktree, against the
proposed base (`4acee87`, unmodified):

```
6 failed, 4632 passed, 337 skipped in 513.35s
```

Exact match to the fingerprint V3B's own doc states
(`docs/company_os_read_efficiency_v3b.md`: "4,632 passed, 6 failed, 337
skipped") and to the six named failures in [[suite-has-14-known-failures]]'s
gitignored-artifact class (`test_neon_proof` + 5× `test_sloped_v25{1,2}_world`,
all `FileNotFoundError` on render output this worktree never generated).
Zero new regressions. No matched job, reviewer session, or Company OS
execution was run.

## 15. Unresolved questions for the next milestone

* Whether to advance `company-os-v1-bootstrap`'s ref to `V3B`'s SHA now that
  it is further ahead (pure bookkeeping, no code risk).
* Whether any of the ten dogfood counters (§3) are worth authoring as real
  `company/engineering` features — a product decision, not something this
  audit can resolve from git history.
* Whether `main` should ever receive Company OS — explicitly out of scope
  here and already gated behind a separate CEO/`permissions.yaml` decision
  per [[company-os-canonical-baseline]].

## FINAL REPORT

```
audit branch: company-os-v1-integration-audit
audit SHA: <set by the commit that follows this doc>
pushed: yes (after commit)
merged: no

branches inspected: 49
Company OS branches: 37 (company-os-v1-*)
related engineering/efficiency branches: 12 (eng-ai-resource-efficiency-v2,
  eng-ai-resource-efficiency-v2-operational, and 10 further eng-* branches)

proposed canonical base: company-os-v1-read-efficiency-v3b
base SHA: 4acee87c5e6f250754b35d7b876eac948a0349f7
reason: already the fullest accepted lineage; no other branch found with
  more accepted behavior; nothing outside it needs integrating

already contained (ANCESTOR):
count: 36
branches: 35 company-os-v1-* branches (all except the two superseded
  plain-named pairs) + eng-ai-resource-efficiency-v2-operational

superseded:
count: 3
branches: company-os-v1-dashboard-observation-identity-fix,
  company-os-v1-youtube-studio-ingestion, eng-ai-resource-efficiency-v2

parallel accepted:
count: 0
branches: (none)

parallel review required:
count: 0
branches: (none)

experimental/rejected:
count: 0
branches: (none beyond the superseded eng-ai-resource-efficiency-v2, already
  counted above)

dogfood-only:
count: 10
branches: eng-attempt-ledger, eng-attempts-remaining,
  eng-attempts-remaining-after, eng-attempts-remaining-consumer,
  eng-blocked-attempts-consumer, eng-blocked-attempts-v3b,
  eng-governance-drift-check, eng-reviews-completed-repoexpl,
  eng-scope-usage, eng-stage-timing

unknown:
count: 0
branches: (none)

highest-risk overlaps:
1. None found requiring integration risk classification (no PARALLEL_ACCEPTED
   branch exists).
2. Naming-trap risk only: -reviewed vs. plain-named pairs (dashboard identity,
   YouTube Studio ingestion) could mislead a future cherry-pick if read by
   name instead of ancestry.
3. eng-ai-resource-efficiency-v2 attempt 1's code (audit.py/routing.py/
   tool_evaluation.py) must not be resurrected — it was deliberately replaced.

proposed integration order:
(none — no PARALLEL_ACCEPTED branch exists to integrate)

branches safe to archive later: company-os-v1-dashboard-observation-identity-fix,
  company-os-v1-youtube-studio-ingestion, eng-ai-resource-efficiency-v2, and
  the 10 dogfood-only eng-* branches listed above
branches that must remain: company-os-v1-read-efficiency-v3b,
  company-os-v1-bootstrap, and every other ANCESTOR branch as historical
  evidence (none block cleanup, but none need cleanup either)

expected final canonical branch name: company-os-v1-read-efficiency-v3b
  itself already qualifies; no new "company-os-v1-integration" branch is
  needed unless the next milestone wants a fresh name for the bootstrap
  ref's fast-forward target

expected integration strategy: none required (already integrated); future
  new product work (if any) authored fresh, not cherry-picked from dogfood

estimated number of integration stages: 0

tests/fingerprint verified: yes — 6 failed, 4632 passed, 337 skipped,
  matches V3B's own documented fingerprint exactly, zero new regressions

current operating-status recommendation: CONTROLLED ROUTINE DOGFOOD
  (unchanged; autonomous engineering remains PAUSED)

next milestone: a product decision on whether any of the 10 dogfood
  counters becomes real Company OS work, and/or the separate main-merge
  decision already gated behind permissions.yaml — neither authorized here

verdict:

COMPANY OS V1 INTEGRATION AUDIT:
PASS
```
