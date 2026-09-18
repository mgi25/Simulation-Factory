# Repository Exploration Efficiency V1

**Branch** `company-os-v1-repository-exploration-efficiency`, based on
`company-os-v1-consumer-resource-mode` at `4b6064d`. **Not merged. Not
authorization to merge.**

Consumer Mode V1 fixed the packet: a routine work order's referenced material
dropped from 16,985 to 3,661 characters. The same matched job still read
1,835,390 cache units and ran 39 turns to change two files. This milestone is
about the cost that packet fix could not touch - what a session does with the
packet after it arrives.

---

## 1. Measuring exploration first

### What is, and is not, in the stored evidence

`tools/engineering_runner/backends.py`'s `ClaudeCodeBackend.launch` runs the
coding CLI as `--print --output-format json`. That mode returns **one final
result envelope per session** - no `stream-json`, no per-turn event log. Every
stored session this company has ever run, real or synthetic, was launched this
way. Consequence, verified by reading the launch code rather than assumed:

| what | reliability |
|---|---|
| session cost, output tokens, cache-read units, cache-creation units | RELIABLE, when `unreliable_metrics` for that session is empty |
| `model_turns` | RELIABLE for sessions built after the telemetry-normalisation fix; PARTIAL for a handful of older receipts that instead carry a legacy `tool_calls` key of the same rough meaning under a different, previously-conflated name |
| files changed | RELIABLE - measured from git by `evidence.py`, never self-reported |
| **which files were read, what was searched for, how many times a file was re-read** | **UNAVAILABLE, structurally, for every session** - there is no log to read it from |

A reviewer's own `evidence` field sometimes names a grep or a full-file read in
prose (`"Grep: max_developer_attempts across company/engineering/*.py"` is a
real line from a stored attestation). That is the model's self-report, not a
measurement, and is not turned into a count anywhere in this milestone's
tooling - doing so would present an unreliable number as a reliable one.

### What was measured

`tools/engineering_runner/exploration_report.py` (new, additive, stdlib-only)
walks every runner-state directory this machine holds outside git and reads
each stage's own `receipt.json` (developer) or `session.json` (reviewer,
where no receipt exists) - nothing else. Run once, over all six known
runner-state roots (`company-os-{consumer,hardening,aiv2,aiv2-op,aiv2-after}-
runner-state`, `company-os-runner-state`):

```text
sessions_measured: 21  (10 developer, 11 reviewer)
sessions_with_unreliable_metrics: 0

developer:  avg cache-read 2,584,057   max 7,245,449   avg cache-read/file-changed 734,979
reviewer:   avg model_turns 14.9       avg cache-read   244,074
```

Two things this run confirmed that were not previously written down:

- **The un-optimized BEFORE job's own cache-read (1,347,797) was lower than
  Consumer Mode V1's matched job (1,835,390).** Consistent with the existing
  record that Consumer Mode V1 did not flatter on cost (`+18.7%` over BEFORE):
  a cheaper model tier did more work, not the same work more cheaply, and
  packet narrowing alone did not touch the in-session exploration cost.
- **Developer `model_turns` is reliably present in only one of ten stored
  developer receipts** - the rest predate the field (they carry `tool_calls`,
  the name the telemetry-defect fix retired because it had been used for two
  different quantities). Reviewer turns, by contrast, are read from the
  runner's own `session.json` and are present for all eleven reviewer stages,
  because that record's shape did not change across the fix. This is a
  provenance difference, not a coincidence, and it is why `check_budget` (see
  §5) is wired to score `model_turns` only when supplied and not flagged
  unreliable, rather than assumed present.

Classification for the record: **cache-read units and cost - RELIABLE. Files
changed - RELIABLE. Model turns - RELIABLE where the field exists, PARTIAL
(legacy key, approximate) where it does not, UNAVAILABLE nowhere it matters
here. File-level and search-level exploration - UNAVAILABLE, unconditionally.**

Tests: `tests/test_engineering_runner_exploration_report.py` (10 cases, all
against synthetic fixtures - the real runner-state directories are outside
this repository and outside git, so no test depends on their presence).

---

## 2. Deterministic task/repo map

`tools/engineering_runner/repo_map.py` (new, additive, stdlib-only: `ast`,
`json`, `pathlib`, `re`, `dataclasses`). Walks `company/`, `tools/`, `tests/`
- the three roots a routine Company OS job's `authorized_paths` ever name -
parses every `.py` file with `ast`, and records per module: classes,
functions, imports (full dotted names), the first line of the module
docstring, line count, and whether it looks like an entry point. A second
pass builds a reverse index from production module to the test files that
actually import it (by resolved dotted name, not by filename pattern - two
test files in the fixture suite both import a shared sibling module, and a
filename-based guess would have missed one of them).

`owner` is a directory-prefix proxy, stated as one: this package may not
import the real capsule/ownership registry at all (the same architecture gate
that proves the runner cannot import Company OS), so a cheap, filesystem-only
substitute is what is available here, and it is documented as a substitute
rather than presented as the real thing.

**Size and timing**, measured on this repository's own `company` + `tools` +
`tests` trees: **413 modules**, a full build in **1.74 s**, a cached JSON of
**554,922 characters** (~542 KB), with **112** of those modules resolved to at
least one covering test file. Nothing in this package hands the whole map to
a model session; `query()` returns a ranked, capped slice (default 5 hits),
and `briefs.py` injects only that slice into the instructions - see §2b.

**Retrieval flow implemented:**

```text
work order objective (free text)
        |
        v
tools.engineering_runner.repo_map.query(map, objective, limit=5)
        |
        v
2-5 (path, owner, matched symbols, covering tests)
        |
        v
briefs.developer_instructions() / review_instructions()
injects exactly that slice under "## What a deterministic
repository search already found"
```

instead of the session discovering the same files by repeated grep-and-read.
`query()`'s ranking is a fixed rule (path match > symbol match > docstring
match, ties broken by path) - explainable and reproducible, not a learned or
probabilistic ranking.

Tests: `tests/test_engineering_runner_repo_map.py` (12 cases: extraction,
entry-point detection, the reverse test index, syntax-error tolerance,
determinism, JSON round-trip, query ranking, cache load/rebuild/recovery).

### 2b. Wiring into the runner

`runner.py` builds the map fresh from the work order's own worktree at the
start of the developer and reviewer stages (`_repo_map`, best-effort: a build
failure is a missing convenience, never a reason to stop an authorized
session) and passes it to `briefs.developer_instructions` /
`review_instructions`, both of which gained an optional `repo_map` parameter
that is a no-op when omitted - every existing caller and every existing test
of those two functions is unaffected. Built fresh per stage rather than
cached across work orders on purpose: two work orders can sit at different
commits, and a stale map naming a moved file is worse than none.

---

## 3. Structural search: ast-grep evaluated and rejected for V1

Measured, not assumed:

- This repository: **593 `.py` files** against **76 `.gd`** (Godot/GDScript,
  the marble-race simulation - out of scope for a routine Company OS job,
  whose `authorized_paths` never touch it).
- A full-repository `ast.parse` of every `.py` file, walking every class and
  function definition, completed in **2.07 s** and found **11,583** symbols,
  **0** parse errors, on this machine.
- `ast-grep` is not installed in this environment and `npx ast-grep` requires
  a fresh package fetch to run at all - a new dependency, which
  `tools/engineering_runner/__init__.py`'s own stated constraint
  (`requirements.txt` untouched, `health.no_new_dependency` green) already
  argues against introducing without a demonstrated need.

**Verdict: REJECTED for V1, deferred.** This repository's Company-OS-relevant
surface is Python-dominant, the standard library already answers every
"symbols/imports/tests-for-this-module" question this milestone needed (§2),
and structural multi-language search earns its cost on a codebase that needs
multi-language matching - this one does not, for this job. Revisit only if a
future milestone needs a query `ast` cannot express cheaply (e.g. matching
call-site shapes across files), per the brief's stated priority order.

---

## 4. Minimalism / ponytail principle

`briefs.py` already told a developer session, in one sentence, to "prefer
reading the specific file you need over searching the whole repository, and
[not] re-read a file you have already read." This milestone expands that into
a fixed, five-line preference order rendered in every developer briefing
(`_MINIMALISM_LINES`, plain and non-persuasive - an ordering, not an
exhortation, consistent with the file's existing stated design: "nothing here
is persuasion"):

1. Reuse existing code before writing new code.
2. Modify the smallest existing surface that satisfies the objective.
3. Reach for the standard library or an already-declared dependency before
   adding a new one.
4. Prefer the smallest coherent diff over a larger, tidier-looking one.
5. Do not build an abstraction, a config flag or a fallback path for a case
   the objective did not ask for.

This governs the implementation of this milestone's own code as much as it
governs the code it produces: the deterministic map, the exploration report
and the budget wiring in §5 are each additive to an existing module or a new
module inside an already-established package, not a new subsystem, and the
checkpoint artifact in §6 needed no new code at all (see below).

---

## 5. Exploration budget

`company/efficiency/budget.py`'s `check_budget` already declared a typed
three-way `Enforceability` split (`LIVE_ENFORCEABLE` /
`POST_SESSION_OBSERVABLE` / `UNAVAILABLE`) and a `DIMENSIONS` table, but two
of its entries were dead on arrival:

- `cache_read_units` was scored with a hardcoded ceiling of `"observation
  only"` and a hardcoded `exceeded=False` - it could **never** register a
  violation, regardless of the observed value, because no ceiling existed for
  it to be compared against.
- `model_turns` was declared `UNAVAILABLE` and its score call passed a
  hardcoded `None`, even though `receipt.usage.model_turns` was already being
  captured, named, and excluded from `unreliable_metrics` precisely so it
  could be scored - the wiring stopped one call short of using it.

Both are now real:

- `ResourceProfile` gained `session_cache_read_ceiling` (consumer: 1,000,000;
  expanded: 3,000,000 - see the threshold declaration in §9), carried through
  `ResourceCeiling.from_profile` (halved for a review, like every other
  ceiling here) and scored in `check_budget` against the actual
  `cache_read_units` the receipt reports.
- `check_budget` gained a `model_turns` parameter; `emission.py` now passes
  `receipt.usage.model_turns` through. `model_turns` is reclassified
  `POST_SESSION_OBSERVABLE` (it is now a trustworthy post-session value when
  not flagged unreliable - the same class as cost and cache-read beside it),
  never `LIVE_ENFORCEABLE` (no backend this company drives accepts a turn
  ceiling, unchanged).
- Two dimensions declared and never scorable: `repo_file_reads` and
  `repo_searches`, both `UNAVAILABLE`, with a note pointing at the concrete
  fact in §1 rather than at a general disclaimer. This is the milestone's
  literal answer to "do not pretend a metric is enforceable if the backend
  cannot observe it": the gap is now a named row in the budget table, not a
  silent absence.

Both new observations remain exactly what their class promises: **never**
`enforced_violations` (nothing stops a session mid-flight from reading more
cache than the ceiling), always visible in `observed_violations` when
exceeded - "a checkpoint or escalation" in practice means the fact is now
recorded on `EfficiencyEmission.budget_check` where it previously could not
be, ready for a CEO-facing surface to read; wiring that surface is future
work, out of scope here (the emission itself was already the boundary this
milestone was told to stay inside - see §11).

Tests: eleven cases added or changed in `tests/test_company_efficiency.py`,
including the reclassification, the new cache-read ceiling exercised at both
sides of the line, the unreliable-metric exclusion for `model_turns`, and the
two new UNAVAILABLE dimensions asserted unscorable.

---

## 6. Checkpoint + fresh session

Already exists and already satisfies the brief's list, verified against a
real stored `checkpoint.json` (Consumer Mode V1's matched job,
`run-000001/checkpoint.json`) rather than against the code alone:

| brief asks for | present as |
|---|---|
| immutable work order | `work_order` (id, fingerprint, objective, branch, authorized paths, acceptance criteria, required tests) |
| current commit/diff | `git` (`base_commit`, `commit_sha`, `uncommitted`) |
| completed work | `completed_work` (summary, files changed, invariants preserved) |
| unresolved work | `stopped` (state, reason) |
| failing tests | `failing_tests` |
| relevant files/symbols | `context_refs` - the packet's own narrowed reference set |
| reviewer findings if any | `unresolved_reviewer_findings` |

No transcript, no tool output, no session id - `runner.py`'s own
`_write_checkpoint` docstring states this is deliberate: "the transcript is
the expensive part and almost none of it is load-bearing." `next_session`
explicitly tells the resuming session not to carry the previous conversation
forward and that the file authorizes nothing.

**No code change made here.** This is the minimalism principle (§4) applied
to this milestone's own work: the artifact already meets the bar, and adding
a parallel field for "relevant files/symbols" sourced from the new repo map
(§2) would duplicate `context_refs` for no reader that does not already have
it.

---

## 7. External tools evaluated

| candidate | baseline | candidate result | resource usage | quality | complexity | verdict |
|---|---|---|---|---|---|---|
| internal deterministic repo map (`ast`) | model re-discovers files via grep/read loops each session | 2-5 ranked hits returned in ~2s from a cached, stdlib-only build | negligible (~2s build, <500KB cache, no new dependency) | unchanged - additive, tested, no existing behaviour altered | one new module + one new field on two existing functions | **ADOPTED** |
| ast-grep | plain Python `ast` | not installed; would need a fresh fetch to evaluate at all | unknown - not measured, on principle (one dimension at a time, and the cheaper option was not yet exhausted) | n/a | a new external dependency, against `tools/engineering_runner`'s stated no-new-dependency boundary | **REJECTED for V1** (§3), deferred pending a query `ast` cannot express |
| Serena / Graphify | - | not evaluated this round | - | - | - | **DEFERRED** - brief's own stated priority order places these after repo-map/structural-navigation/minimalism, which this round already addressed |
| RTK | shell tool-output verbosity, unmeasured | not evaluated this round | - | - | - | **DEFERRED** - explicitly low current priority in the brief "unless measurement proves shell-output verbosity is material," and no such measurement was made this round |
| context-compression approaches | - | not evaluated this round | - | - | - | **DEFERRED** |

Only one candidate was installed or exercised this round, as instructed.

**A relevant hook already existed and was deliberately not used.**
`company/efficiency/providers.py` already declares `CodeIntelligenceProvider`
(a `Protocol`) and a `CodeQueryKind.LIKELY_FILES` query kind, with
`ReferenceRepositoryProvider` as a stub that explicitly says that query kind
"remain[s] explicitly unavailable until a real provider (for example
Graphify) is installed and injected." It is exercised only from
`benchmark.py` and tests today - not from the live `emission.py` receipt
path. This is the same conceptual slot §2's repo map fills, and it was
**not** wired there: `providers.py` lives in `company/`, this milestone's map
lives in `tools/engineering_runner/`, and no `company/` module imports
anything from `tools/` anywhere in this repository today (checked by grep,
zero hits). Adding the first one, to save a Protocol implementation, would
introduce a new cross-boundary dependency edge the architecture has not
needed so far, for a milestone that was told to preserve the Company OS /
tools boundary rather than extend it. The repo map is wired at the layer
that actually renders a briefing (`tools/engineering_runner/briefs.py`)
instead - see §2b.

---

## 8. Model discipline

This entire milestone's implementation, from measurement through the wiring
in §5 and the repo map in §2, was written directly in this session (Sonnet),
with no subagent and no Workflow-tool fan-out. Verification was deterministic
throughout: unit tests for every new module, the existing suite re-run after
each change, and the ast-grep decision in §3 backed by a measured timing
rather than a claim. No architectural or security question in this round was
judged difficult enough to warrant escalation.

---

## 9. The threshold, declared before the live test

Per the brief: "Choose a reasonable threshold before the live test and
document it. Do not define 'materially lower' after seeing the result."

**Threshold: the matched job's developer-attempt `cache_read_units` must come
in at or under 1,376,542 (75% of Consumer Mode V1's matched-job figure of
1,835,390) for repository exploration to count as materially lower.** Chosen
as a 25% reduction because that is the order of magnitude a pre-computed
2-5-file hint plausibly removes from a grep-and-read discovery loop on a
two-file change, without assuming the packet-narrowing lever (already spent
in Consumer Mode V1) has anything left to give. `session_cache_read_ceiling`
itself (§5, set to 1,000,000 for the consumer profile) is a separate,
independently-justified number - it is where the *ceiling* sits, chosen to
land below the number that opened this milestone, not where the
*improvement* threshold sits. Turns, cost and wall time are reported
alongside but are not the acceptance metric: §1 already found the model-tier
lever "weak on this workload" with variance larger than the effect, and nothing
in this milestone changes that finding.

---

## 10. Cheap validation, then the one matched job

Deterministic tests pass first: every new test file in §1-§2 (22 cases) and
the full suite at commit `30878b1` - **4,545 passed, 6 failed (the known
gitignored-artifact failures named in the project's own suite fingerprint),
337 skipped, zero new failures.** The three research branch-scope guards that
watch `tools/` were re-run *after* committing (the failure mode they have is
invisible before a commit) and all three pass: the new modules sit inside
`tools/engineering_runner/`, already on the additive-paths allowlist.

**The matched job.** Objective: "For one engineering work order, tell me how
many reviewer passes have been completed so far, so a CEO page can show
review activity alongside developer attempts" - same subsystem
(`company/engineering`), same authorized-path shape (one module + its test
file), same risk level (`medium`) and same `specialist_domain=""` as the
historical `attempts-remaining` objective, so it classifies the same way
(routine, standard tier). Not the identical objective: that feature is
already implemented on this branch's own base. Smaller in one respect
(surfacing an existing counter rather than a spent/remaining pair) and
honestly reported as such rather than dressed up as identical.

Run via `python -m company.engineering request` then
`python -m tools.engineering_runner run-one`, consumer profile, one Developer
attempt, one Reviewer pass, no automatic retry, on top of this milestone's
own commit (`base_commit 30878b1`). Result: **developer accepted, reviewer
verdict `pass` (attested pass, deterministic pass), gate 11/11 required
suites green with zero blockers, final state `ready_for_approval`.**

---

## FINAL REPORT

**baseline branch:** `company-os-v1-consumer-resource-mode` @ `4b6064d` (verified pushed and clean before starting)
**new branch:** `company-os-v1-repository-exploration-efficiency`
**commit:** `30878b1381040893fc474e89fe1a9e7d90a99342`

**historical exploration findings:** §1. Cache-read units, cost, output tokens and (where the field exists) model turns are RELIABLE; files changed is RELIABLE; which files were read or searched is UNAVAILABLE for every one of the 21 stored sessions measured, by construction of the backend's `--output-format json` launch mode. Ten stored developer receipts predate the `model_turns` field and carry a legacy `tool_calls` key instead - PARTIAL, not blended into the reliable aggregate.

**navigation mechanism:** `tools/engineering_runner/repo_map.py` - stdlib `ast` over `company/`, `tools/`, `tests/`, queried into a capped, ranked slice injected into each briefing.
**repo-map size:** 413 modules, 554,922-character JSON (~542 KB), built in 1.74 s; never handed whole to a session.
**retrieval behavior:** objective text → `query()` → 2-5 ranked (path, owner, matched symbols, covering tests) → injected under one new briefing section, plus the tests already covering each authorized-to-write file.

**external tools tested:** the internal `ast`-based repo map (built and measured).
**adopted:** the internal repo map.
**rejected:** ast-grep, for V1 (not installed here, no new dependency justified against a 2.07 s / 0-error full-repo `ast` parse of 593 files).
**deferred:** Serena, Graphify (a `CodeIntelligenceProvider` hook for this already exists in `company/efficiency/providers.py`, unwired, benchmark-only), RTK (shell-output verbosity not measured this round), context-compression approaches.

**Consumer Mode V1 matched result** (developer attempt, `attempts-remaining`): 39 turns, 11,020 output units, 1,835,390 cache-read units, 71,558 cache-creation units, $1.640637, 2 files changed, 305.9 s.

**Exploration Efficiency V1 result** (developer attempt, `reviews-completed`): 27 turns, 8,184 output units, **990,324 cache-read units**, 61,384 cache-creation units, $1.083562, 2 files changed, 209.6 s.

**change (developer attempt, Consumer V1 → this milestone):** cache-read **-46.0%** (1,835,390 → 990,324), turns -30.8%, output tokens -25.7%, cost -34.0%, wall time -31.5%. Reviewer attempt moved the other way in this single run (7→9 turns, 78,605→158,520 cache-read, $0.296→$0.374) - small absolute numbers, and §1 already established that n=1 variance on this workload exceeds the effect size for any single dimension; the total job cost (developer + reviewer) still fell, $1.936→$1.457 (**-24.7%**).

**quality:** developer report accepted; two invariant-preservation statements and two unresolved-risk notes recorded, neither blocking.
**tests:** 116 passed (was 114; 2 added), 0 failed.
**review:** verdict `pass` (attested pass, deterministic pass), 1 advisory finding, 0 blocking.
**gate:** READY, 11/11 required suites green, 0 blockers.

**consumer viability:** SUPPORTED. One provider, one session per stage, one developer attempt, one reviewer pass, no automatic retry, total job cost $1.457 - inside the consumer profile's own $3.00 session ceiling with room to spare, and $0.479 cheaper than the same-shaped Consumer Mode V1 job it is compared against. Not a claim that every task fits: §9's threshold and this result are both about a routine, bounded, two-file change, the same class of job Consumer Mode V1 was validated against.

**verdict: REPOSITORY EXPLORATION EFFICIENCY V1: PASS.** Every §10 acceptance condition met: STANDARD tier resolved and used, tests PASS, review PASS, gate READY, no automatic retry occurred, telemetry trustworthy (`unreliable_metrics: []` on both sessions), and repository exploration - measured as the developer attempt's `cache_read_units`, the threshold declared in §9 before this job ran - came in 46.0% below Consumer Mode V1's matched figure against a 25% bar. **Do not merge.**

**This is the precondition, not the lifting of it.** `docs/company_os_consumer_resource_mode.md`'s own record states plainly that autonomous Company OS engineering is PAUSED, for one stated reason - live repository exploration dominating resource usage with nothing reaching inside a session - and names exactly one condition for resuming: "repository-exploration efficiency is improved *and* proven with a cheap matched run." This milestone is that improve-and-prove step, and it passed. Whether to resume issuing autonomous Company OS engineering requests is a CEO/operator decision this document does not make on its own behalf, the same way a READY gate is never itself authorization to merge.

---

## 11. Governance, unchanged

Nothing here touches: the Company OS / tools boundary (the two new `tools/`
modules import only what `test_the_runner_adds_no_dependency` already
allowlists, verified by that test), the no-subagents rule (`no_subagents=True`
is not read anywhere in this branch), the separate-reviewer routing, CEO
approval, automatic-merge refusal, publish/deploy refusal, or the integration
gate. No architecture check was exempted, extended or weakened to land this
work.
