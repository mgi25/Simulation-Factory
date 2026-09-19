# Job B (executed, READY) and Job C (stopped before execution)

**Status: REAL PRODUCTION-LIKE DOGFOOD for Job B, not benchmark evidence.** Same
orchestration code and the same `tools/engineering_runner` external runner as
[`docs/company_os_supervised_burnin.md`](company_os_supervised_burnin.md) (Job A) and
[`docs/company_os_supervised_burnin_correction.md`](company_os_supervised_burnin_correction.md)
(Job A's correction), spawning real `claude` CLI subprocesses against the real Anthropic
API. Job C was deliberately never submitted — see part 3.

## Part 1 — Phase 1: integrating the approved correction

The CEO approved `532ce7a31ece35a48c5aed8cf61ce83976ab1b03` (Job A's correction,
`wo-req-attempts-remaining-null-safe`) for the burn-in lineage only, not for `main` or
`company-os-v1-bootstrap`. It was cherry-picked onto `company-os-v1-supervised-burnin`
(then at `c59658f`) as `a0a6b81abb49dfc07a64eceb54d0d82b3cfdfc4e`:

- `git cherry-pick 532ce7a3` applied with **zero conflicts**.
- `git diff --stat c59658f..a0a6b81` shows exactly the two files the correction's own
  reviewer approved: `company/engineering/result.py` (16 changed) and
  `tests/test_company_engineering_execution.py` (40 changed) — identical to the diff stat
  on the source commit.
- `git log --oneline c59658f..a0a6b81` shows exactly one commit — no unrelated history.
- `pytest tests/test_company_engineering_execution.py -q` → **140 passed**.
- `main` stayed at `8b1022aec899c7fa72ca77f2a1441c4d1b4ff48f`; `company-os-v1-bootstrap`
  stayed at `b84f8a75a2d4aaeefd88798f23bc5948e7d39195` (checked via
  `git ls-remote origin` before and after). Neither was fetched, rebased onto, or written
  to.
- Pushed: `origin/company-os-v1-supervised-burnin` now at `a0a6b81`.

## Part 2 — Job B: section-header renumbering (executed, READY)

**Dry-run intake** (scratch state dir, before any real submission):
`specialist_domain: ""`, `resource_profile: consumer`, `escalation: none`,
`specialist_reason: "the objective names no security, governance, architecture or
concurrency work and the risk is not high, so this is routine implementation"`. No manual
wording adjustment was needed for Job B (unlike the correction job, whose objective had to
be reworded to drop "redesign"/"migration" — see the classifier defect note below).

- **Work order:** `wo-req-test-section-header-renumber` (fingerprint `08be23cd4f3b7c53`)
- **Request:** `req-test-section-header-renumber`, base commit `a0a6b81` (post-integration
  tip)
- **Write scope:** `company/engineering`, `tests/test_company_engineering_execution.py`
  (capsule `company-engineering-execution`, same as Job A)
- **Defect fixed:** four `# --- N.` section-header banners in
  `tests/test_company_engineering_execution.py` were duplicated/out of order — a second
  `15.` at line 1884 (immediately followed by a `16.` at line 1947 that then collided with
  it), and `12.`/`13.` each reappearing a second time near the end of the file (lines 2238,
  2449) despite those numbers already being used earlier (lines 1575, 1659).

**Developer** (session `fba3d6a1-dc6f-4be0-b13b-1c824e5a8223`, employee
`software_implementation_engineer`, packet `6cda69f9fdbc8a0c` attempt 1, authority
`6bceb7c1b4d00456`):
- Commit `0bb362842fdac7f8419cb03df5ac9b5fd08e5df8` on branch
  `eng-test-section-header-renumber`, pushed, remote-verified.
- Changed exactly `tests/test_company_engineering_execution.py` — **4 lines** (4
  insertions, 4 deletions): `15.`→`16.` (line 1884), `16.`→`17.` (line 1947),
  `12.`→`18.` (line 2238), `13.`→`19.` (line 2449). Verified independently: the file's
  banners now read `1, 2, 3, ..., 19` with no duplicate and no inversion.
- Attempt 1 of 1. `outcome: accepted`.

**Reviewer** (session `3b86adb8-213e-4651-b564-10fafb4a2647`, employee `chief_architect`,
disjoint, read-only, `may_write: []`):
- **Verdict: `pass`.** Findings: none. `read_only.json`: 0 violations.

**Deterministic QA:** `tests/test_company_engineering_execution.py` — 140 passed in
14.04s (unchanged pass count from before the renumbering, confirming zero behavior
change).

**Gate:** `READY` (`integration-readiness-2026-09-20-8c2397783bdfa34a`), 11/11 required
suites green, 0 blockers.

**Final state:** `ready_for_approval`. Not merged, not approved by this run.

### Job B telemetry (real, provider-reported, `usage_source: model_usage_totals`)

| | Developer | Reviewer |
|---|---:|---:|
| model | claude sonnet (`claude_code`, `model_tier: standard`) | claude sonnet (`claude_code`, `model_tier: standard`) |
| provider | anthropic | anthropic |
| input tokens (fresh) | 19 | 6 |
| output tokens | 3,744 | 2,358 |
| cache-creation tokens | 24,210 | 15,449 |
| cache-read tokens | 276,846 | 29,798 |
| cost (USD) | 0.38343049999999995 | 0.17043524999999998 |
| wall time | 81.719 s | 48.189 s |
| model turns | 14 | 4 |
| tool calls (edits+grep) | 4+2 = 6 | 0+1 = 1 |
| files touched | 1 (`tests/test_company_engineering_execution.py`) | 1 (read-only) |
| retries | 0 | 0 |

**Job B total cost: $0.5538657499999999.** Total wall time: 81.719 s + 48.189 s =
**129.91 s**.

### Job B authority audit

| | Developer | Reviewer |
|---|---|---|
| Authority fingerprint | `6bceb7c1b4d00456` | separate snapshot, read-only |
| Work order / packet | `08be23cd4f3b7c53` / `6cda69f9fdbc8a0c` (attempt 1) | same work order, reviewer packet |
| may_write | `company/engineering`, `tests/test_company_engineering_execution.py` | `[]` |
| actual files modified | `tests/test_company_engineering_execution.py` | none (0 violations) |
| every modified file permitted? | **yes** | **yes** |
| authority refusal occurred? | no | no |

## Part 3 — Job C: stopped before execution (schema pre-flight failed)

**The CEO's brief for Job C required a pre-implementation check: "Before implementation
verify the actual telemetry schema contains a stable existing identifier suitable for
deterministic deduplication. If no stable identifier exists: STOP rather than inventing
one." That check was run, and it fails.** No request was submitted, no work order was
created, no developer or reviewer session ran, and no money was spent on Job C.

**What was checked, and what it found:**

1. `ai_platform/usage.py:83-123` (`ResourceUsageRecord`, the record type the runner
   actually writes to `docs/evidence/.../resource_usage/<work-order>/NNNNNN.json` — see
   e.g. `resource_usage/wo-req-attempts-remaining-null-safe-9c9ba66627bb/000001.json` from
   this same burn-in) declares: `task_id`, `reasoning_class`, `outcome`, nine
   `context_*` fields, `passes`/`retries`/`cache_hits`/`retrieval_hits`/`subagents_used`,
   `tool_calls`/`input_units`/`output_units`/`usage_unit`/`duration_s`,
   `rejection_reason`, `notes`. **No field identifies a specific measured response or
   event.** `task_id` is shared by every attempt against the same work order (confirmed
   in this very burn-in: Job A and its correction share no id collision only because they
   are different work orders, but two attempts *within* one work order would carry the
   identical `task_id`), and nothing else in the record distinguishes one provider
   response from another.
2. `company/finance/usage_cost.py:97-103` (`OBSERVED_ATTRIBUTES`) confirms what
   `observe_usage()` is even able to read off a `ResourceUsageRecord`: `passes`,
   `retries`, `expansion_count`, `required_expansion_count`, `expansion_chars`. No
   identifier is among them.
3. `company/finance/usage_cost.py:208-236` (`UsageObservation`) and
   `company/finance/usage_cost.py:332-413` (`observe_usage`) show the one thing that
   looks like an identifier, `usage_ref`, is **not part of the usage-record schema at
   all** — it is a required keyword argument the *caller* supplies (line 335), copied
   through unchanged (line 370/395). Per
   [[company-os-usage-cost-dogfood-stop-condition]] (recorded when this bridge was
   built), the CLI's caller derives it from **the store's file sequence position** —
   an artifact of where a record happened to land on disk, not a fact the provider
   reported about the response itself. Two independent re-imports of the same underlying
   event into two different store positions would get two different `usage_ref`s; two
   unrelated events written back-to-back would not collide only by chance.
4. `usage_fingerprint` (also on `UsageObservation`, defaulting to `record.fingerprint()`)
   is a content digest, not an event identity: it would correctly catch a byte-for-byte
   duplicate write of the same record, but the CEO's brief asks for deduplicating
   "records that represent the same measured response/event" — which, per the accepted
   finding in [[company-os-usage-cost-dogfood-stop-condition]] and
   [[company-os-real-evidence-acceptance-stop-condition]] ("one API response is written
   as several rows repeating one usage block"), is precisely the case where the rows are
   **not** byte-identical (they can legitimately differ in which row carries which
   sub-slice of the same underlying response) and a content fingerprint would fail to
   merge them, while two textually-identical but genuinely separate measurements would be
   wrongly merged by it. Neither failure mode is acceptable for a dedup utility, and nothing
   in the schema distinguishes the cases.

**Conclusion: no field anywhere in the actual telemetry schema — `ResourceUsageRecord`,
`UsageObservation`, or the identifiers derived from either — is a stable, intrinsic
identity for "the same measured response/event" that a deterministic utility could key
on without either the caller inventing one (which the CEO explicitly forbade) or the
utility silently redefining "duplicate" as "byte-identical" (which does not match the
brief's own stated purpose, and which the real-evidence-acceptance finding shows would
miss the actual known case).**

**Disposition:** Job C is **not selected for implementation as briefed.** No capsule
ownership question, no risk classification, and no dry-run intake were exercised, because
the schema check that gates implementation failed first — exactly the order the CEO's
brief specified ("before implementation verify..."). This is recorded as a legitimate,
evidenced stop, not a systemic Company OS defect: the orchestration, intake and
authority machinery were never engaged for Job C, so they neither passed nor failed
anything.

## Part 4 — known classifier defect (recorded, not fixed)

Per the CEO's explicit instruction, this is recorded and **not fixed in this pass**.
`company/engineering/intake.py`'s `SPECIALIST_TRIGGERS["architecture"]` matches the bare
substrings `"redesign"` and `"migration"` anywhere in an objective or constraint, with no
distinction between an instruction proposing that work and a constraint forbidding it
("do not redesign...", "no migration machinery..."). This was hit while drafting the
correction job's request (see
[[company-os-supervised-burnin-job-a-correction-stop-condition]]) and is now recorded a
second time here as the same class of defect. It was checked for and **not present** in
either Job B's or (had it proceeded) Job C's objective wording — both were dry-run
validated first, per the CEO's standing instruction, and Job B returned
`specialist_domain: ""` with no manual rewording needed.

**Status: `KNOWN_CONTROL_PLANE_DEFECT`.** Does not block continued supervised burn-in,
because deterministic dry-run intake reliably detects the escalation before any real
submission. Does block any future decision to enable routine autonomous engineering,
since an autonomous run has no CEO in the loop to notice and reword a false escalation
(or, worse, an unnoticed failure to escalate a genuinely architectural change whose
objective happens to avoid these exact substrings).

## Part 5 — aggregate telemetry: correction + Job B + Job C

Job C spent nothing (no session ran). Aggregating the correction job
(`wo-req-attempts-remaining-null-safe`, from
[`docs/company_os_supervised_burnin_correction.md`](company_os_supervised_burnin_correction.md))
and Job B:

| | Correction | Job B | Combined |
|---|---:|---:|---:|
| developer cost | $0.7904202499999998 | $0.38343049999999995 | $1.1738507499999997 |
| reviewer cost | $0.3853885 | $0.17043524999999998 | $0.5558237499999999 |
| **total cost** | **$1.1758087499999998** | **$0.5538657499999999** | **$1.7296744999999997** |
| wall time (dev + rev) | 368.29 s | 129.91 s | 498.20 s (~8.3 min) |
| model turns | 18 + 5 = 23 | 14 + 4 = 18 | 41 |
| input tokens | 22 + 7 = 29 | 19 + 6 = 25 | 54 |
| output tokens | 10,620 + 7,842 = 18,462 | 3,744 + 2,358 = 6,102 | 24,564 |
| cache-creation tokens | 68,627 | 39,659 | 108,286 |
| cache-read tokens | 570,390 | 306,644 | 877,034 |
| developer attempts used | 1 | 1 | 2 |
| reviewer passes used | 1 | 1 | 2 |
| retries | 0 | 0 | 0 |

Adding Job A's own original (rejected) attempt from
[`docs/company_os_supervised_burnin.md`](company_os_supervised_burnin.md) ($0.6211715 +
$0.4425192499999999 = $1.0636907499999999) for a whole-burn-in-to-date total across all
real sessions run so far (Job A + correction + Job B; Job C never ran): **$2.793365 across
4 developer attempts and 4 reviewer passes.**

## Part 6 — runtime/control defects, interventions, retries

- **Runtime/control defects observed this phase:** none in the orchestration, intake,
  authority, receipt, review-adjudication, or gate machinery. The one recorded defect
  (Part 4) is in the intake *classifier's keyword matching*, not in job execution, and it
  was caught by the dry-run step the process already requires — it did not cause an
  incorrect real-job outcome.
- **Manual interventions required:** none for Job B. Job C required no manual repair
  either — its schema check is itself the manual verification step the CEO's brief asked
  for, run before any automated stage began.
- **Automatic retries/continuations:** zero. One developer attempt and one reviewer pass
  for Job B, no retry of either. Job C's stop was not a retry-eligible failure — nothing
  was submitted to retry. No job was started after Job C's stop.
- **No subagents:** all orchestration in this phase (cherry-pick and verification,
  drafting and dry-running Job B's and Job C's requests, invoking
  `python -m company.engineering request` and `python -m tools.engineering_runner
  run-one`, reading back results, writing this report) was performed serially in this
  controlling session. The only separate processes spawned were the Job B developer and
  reviewer `claude` CLI subprocesses via `tools/engineering_runner` — the system under
  test, not orchestration subagents.

## Part 7 — success/burn-in classification

Per the CEO's stated rule:

- Correction job: `READY` (reviewer pass, deterministic QA pass, gate READY) — counts as
  successful supervised real job #1.
- Job B: `READY` (reviewer pass, deterministic QA pass, gate READY) — successful
  supervised real job #2.
- Job C: never submitted; a legitimate, evidenced pre-flight stop, not a systemic
  failure — contributes neither a pass nor a failure to the count, per the same rule
  applied to Jobs B/C in the original burn-in.

**Successful supervised real jobs to date: 2** (correction, Job B). Job A's original
attempt (`changes_required`) and Job C (schema pre-flight stop) are both legitimate
non-`READY` outcomes with no systemic/runtime/control defect underneath them.

**Burn-in result:** `READY_FOR_MORE_SUPERVISED_REAL_JOBS`.

**Autonomy blocker status:** `AUTONOMY_DECISION_BLOCKED_BY_INTAKE_CLASSIFIER_DEFECT`, per
Part 4 — unresolved, recorded, deliberately not fixed in this pass per the CEO's
instruction.

## Part 8 — evidence paths

- `docs/company_os_supervised_burnin_b_and_c.md` (this file)
- Job B: `docs/evidence/company_os_supervised_burnin/engineering/{requests,work_orders,plans,jobs,reviews,results,attestations,gate_verdicts}/…wo-req-test-section-header-renumber…`,
  `docs/evidence/company_os_supervised_burnin/execution/{packets,receipts,authorities,efficiency}/…wo-req-test-section-header-renumber…`,
  `docs/evidence/company_os_supervised_burnin/resource_usage/wo-req-test-section-header-renumber-f0defd750274/000001.json`
- Job B raw runner state and transcripts (outside this repository):
  `C:\Users\mgial\OneDrive\Documents\projects\company-os-supervised-burnin-runner-state\runs\wo-req-test-section-header-renumber-f0defd750274\run-000001\`
- Job B implementation branch: `eng-test-section-header-renumber` @
  `0bb362842fdac7f8419cb03df5ac9b5fd08e5df8` (pushed, remote-verified, **not merged
  anywhere**)
- Job C: no work order, packet, receipt, or runner-state directory exists (nothing was
  submitted). This document's Part 3 is the entire evidence record for the stop.
- Correction integration: `company-os-v1-supervised-burnin` @
  `a0a6b81abb49dfc07a64eceb54d0d82b3cfdfc4e` (cherry-pick of `532ce7a3`, pushed). Job B's
  own implementation commit (`0bb36284`) is **not** integrated into the burn-in branch —
  only its evidence is, exactly as Job A's and the correction's implementation branches
  were reported on without being merged, pending a future CEO integration decision. This
  document's own commit lands on top of `a0a6b81` — see the final branch SHA reported
  alongside this run.
