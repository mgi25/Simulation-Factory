# Job A correction — `EngineeringResult` null-safe `developer_attempts_remaining`

**Status: REAL PRODUCTION-LIKE DOGFOOD, not benchmark evidence.** Same orchestration code
and the same `tools/engineering_runner` external runner as
[`docs/company_os_supervised_burnin.md`](company_os_supervised_burnin.md) (Job A), spawning
real `claude` CLI subprocesses against the real Anthropic API.

## Why this job exists

Job A (`wo-req-legacy-attempts-remaining-default`, implementation commit `02828c0a`) was
reviewed `changes_required`: the reviewer (`chief_architect`) found that once a result
whose `developer_attempts_remaining` is `None` is persisted via `to_dict()`, the key
round-trips as JSON `null`, and `from_mapping` then calls `int(null)`, raising `TypeError`.
The CEO declined to approve or merge `02828c0a`, declined to reopen or retry Job A (its one
authorized developer attempt is spent), and authorized exactly one new, separately budgeted
work order to fix the reviewer's finding. **Job A's evidence, branch and commit are
untouched by this job** — see the confirmation section below.

## A. New work order

- **Work order:** `wo-req-attempts-remaining-null-safe` (fingerprint `86d81e400af2e4c0`)
- **Request:** `req-attempts-remaining-null-safe`
- **Base commit:** `313ed4e717ed6c1e9b1e035672522a36e2320580` (this burn-in branch's own
  tip, which already carries Job A's report but not Job A's rejected code change — verified
  before submission: `company/engineering/result.py` at this base still has the pre-Job-A
  `int = 0` default).
- **Intake validation:** dry-run in a scratch state directory returned `"outcome":
  "authorized"` with `specialist_domain: ""` (routine implementation, `model_tier:
  "standard"`) before being submitted for real. The objective's first draft used the words
  "redesign" and "migration", which `company/engineering/intake.py`'s `SPECIALIST_TRIGGERS`
  reads as architecture-specialist work (escalating past the CEO's "one STANDARD developer"
  policy); the objective was reworded to remove both trigger words and re-validated before
  the real request was submitted.
- **Write scope:** `company/engineering`, `tests/test_company_engineering_execution.py`
  only — identical `authorized_paths`/`forbidden_paths` to Job A, since both are owned by
  capsule `company-engineering-execution`.
- **Resource profile:** `consumer`, 1 developer attempt, 1 reviewer pass, `model_tier:
  standard` (confirmed in the reviewer's own briefing artifact) — no specialist or
  strongest-tier escalation.

## B. Result

**Lifecycle:** `requested -> planning -> developing -> testing -> reviewing -> gate ->
ready_for_approval`.

**Developer** (session `f9313602-e947-4180-8f10-9cf2622905cc`, employee
`software_implementation_engineer`, packet fingerprint `a6bdaf63a8e96501`, authority
fingerprint `f74950034183d868`):
- Commit `532ce7a31ece35a48c5aed8cf61ce83976ab1b03` on branch
  `eng-attempts-remaining-null-safe`, pushed and remote-verified (`remote_verified: true`,
  `remote_branch_sha` matches the local commit).
- Changed exactly `company/engineering/result.py` (10 insertions / 6 deletions) and
  `tests/test_company_engineering_execution.py` (40 insertions) — nothing outside the
  granted `may_write` set.
- **The semantic correction** (`company/engineering/result.py`):
  - Field declaration unchanged in shape: `developer_attempts_remaining: int | None = None`
    (same type Job A used; not touched further, per "do not redesign the schema").
  - `__post_init__`: the type check now short-circuits when the value is `None`, only
    validating `int`-ness when a value is present — accepts `None`, rejects anything that
    is neither `None` nor a non-bool `int`, message updated to "must be an integer or
    null".
  - `from_mapping` (the actual defect): replaced
    `int(data.get("developer_attempts_remaining", 0))` with
    `None if (_dar := data.get("developer_attempts_remaining")) is None else int(_dar)`.
    `Mapping.get` already returns `None` for both an *absent* key and a key explicitly
    mapped to JSON `null`, so this one expression unifies both safe cases and only calls
    `int()` on an actually-present, non-null value — exactly the reviewer's own suggested
    fix ("treat a present-but-None value the same as an absent key").
  - `render_text`: prints `"unknown"` for `None`, `str(int)` otherwise — unchanged for
    every non-null case.
- Self-reported test run: `tests/test_company_engineering_execution.py` — 140 passed in
  12.05s.
- Self-disclosed risk (unresolved, informational, not a defect): if
  `EngineeringJob.corrections_remaining` itself ever returned `None`, the field would
  legitimately read `"unknown"` rather than error — noted as intentional per the work
  order's own semantics.
- Attempt 1 of 1 authorized. `outcome: accepted`.

**Reviewer** (session `45659a22-9105-4317-95a5-92a2ae3f0a65`, employee `chief_architect`,
disjoint from the implementer, read-only packet, `may_write: []`):
- **Verdict: `pass`.** All 10 acceptance criteria satisfied with a cited evidence
  reference each (absent-key, explicit-zero, positive-integer, null-round-trip, the
  to_dict+from_mapping round trip, `render_text`, no-other-field-changed, the new focused
  test, full suite pass, no regression).
- **Findings: none.** The reviewer's notes explicitly credit the walrus-operator expression
  as "the smallest possible change" and confirm no unauthorized path was touched.
  `read_only.json`: 0 violations (`HEAD` and worktree status checked before and after
  review).
- One thing the reviewer flagged as *not itself verified*: `ai_platform.serde`'s
  `to_jsonable` behavior for `None` fields was not re-read this pass (it was read during
  Job A's review and confirmed there: `to_jsonable(None)` returns `None`, so the key is
  retained as JSON `null` rather than dropped) — the reviewer noted the new test does not
  depend on that detail either way, since it constructs the `null` mapping directly.

**Deterministic QA:** targeted suite `tests/test_company_engineering_execution.py` — 140
passed (worst-verdict-wins had nothing to override here, since both deterministic QA and
the attested review agree: `pass`).

**Gate:** `READY` (`integration-readiness-2026-09-20-46a611491c3e1718`), 11/11 required
suites green, 0 blockers.

**Where it stopped:** `ready_for_approval`. Per the CEO's standing rule
(`company/engineering/result.py`'s own `NOT_AN_APPROVAL` text, printed on every result),
this is a request to be read, not an approval — nothing here merges, deploys or publishes,
and this run performed no merge (`merge_performed: false` on the receipt).

## C. Telemetry (real, provider-reported, `usage_source: model_usage_totals`)

| | Developer | Reviewer |
|---|---:|---:|
| model | claude sonnet (`claude_code` backend, `model_tier: standard`) | claude sonnet (`claude_code` backend, `model_tier: standard`) |
| provider | anthropic | anthropic |
| input tokens (fresh) | 22 | 7 |
| output tokens | 10,620 | 7,842 |
| cache-creation tokens | 42,717 | 25,910 |
| cache-read tokens | 515,658 | 54,732 |
| cost (USD) | 0.7904202499999998 | 0.3853885 |
| wall time | 231.896 s | 136.392 s |
| model turns | 18 | 5 |
| retries | 0 | 0 |

**Total cost: $1.1758087499999998.** Total wall time: 231.896 s + 136.392 s = **368.29 s**
(~6.1 minutes), sequential, plus the gate stage (11 required suites).

## D. Authority audit

| | Developer | Reviewer |
|---|---|---|
| Authority fingerprint | `f74950034183d868` | separate snapshot, read-only |
| Work order / packet | `86d81e400af2e4c0` / `a6bdaf63a8e96501` (attempt 1) | same work order, reviewer packet |
| may_write | `company/engineering`, `tests/test_company_engineering_execution.py` | `[]` (read-only) |
| may_not_modify | `ai_platform/policy.py`, `company/agent_contract.schema.yaml`, `company/constitution.md`, `company/integration`, `company/integration/checks.py`, `company/integration/policy.py`, `company/integration/suites.py`, `company/org_registry.yaml`, `company/permissions.yaml`, `company/runtime`, `company/task_handoff.schema.yaml`, `company/validation/no_subagents.py`, `sloped`, `tools` | n/a |
| actual files modified | `company/engineering/result.py`, `tests/test_company_engineering_execution.py` | none (`read_only.json`: 0 violations) |
| every modified file permitted? | **yes** | **yes** |
| authority refusal occurred? | no | no |

**Result: zero unauthorized writes.**

## E. Confirmation Job A is untouched

- `eng-legacy-attempts-remaining-default` @ `02828c0ad3097af8a99f0c5bfa6dc4c4939b966d`:
  not merged into this correction's branch, not merged into `company-os-v1-supervised-burnin`,
  not merged into `company-os-v1-bootstrap`, not merged into `main`. Its own evidence
  (`docs/evidence/company_os_supervised_burnin/job_a/**`, the `wo-req-legacy-attempts-remaining-default`
  records) was not read-write touched by this job; this job's records live under a
  disjoint work-order id (`wo-req-attempts-remaining-null-safe`).
- `main` at `8b1022aec899c7fa72ca77f2a1441c4d1b4ff48f` — unchanged (verified via
  `git ls-remote origin refs/heads/main` before and after this job).
- No further burn-in job (B or C) was requested, authorized, or run.

## F. Evidence paths

- `docs/company_os_supervised_burnin_correction.md` (this file)
- `docs/evidence/company_os_supervised_burnin/engineering/requests/req-attempts-remaining-null-safe-96406119a9bf/000001.json`
- `docs/evidence/company_os_supervised_burnin/engineering/work_orders/wo-req-attempts-remaining-null-safe-9c9ba66627bb/000001.json`
- `docs/evidence/company_os_supervised_burnin/engineering/plans/wo-req-attempts-remaining-null-safe-9c9ba66627bb/000001.json`
- `docs/evidence/company_os_supervised_burnin/engineering/jobs/wo-req-attempts-remaining-null-safe-9c9ba66627bb/000001.json` .. `000006.json`
- `docs/evidence/company_os_supervised_burnin/engineering/reviews/wo-req-attempts-remaining-null-safe-9c9ba66627bb/000001.json`
- `docs/evidence/company_os_supervised_burnin/engineering/results/wo-req-attempts-remaining-null-safe-9c9ba66627bb/000001.json`, `000002.json`
- `docs/evidence/company_os_supervised_burnin/engineering/attestations/wo-req-attempts-remaining-null-safe-9c9ba66627bb/000001.json`
- `docs/evidence/company_os_supervised_burnin/engineering/gate_verdicts/wo-req-attempts-remaining-null-safe-9c9ba66627bb/000001.json`
- `docs/evidence/company_os_supervised_burnin/execution/packets/wo-req-attempts-remaining-null-safe-9c9ba66627bb/000001.json`, `000002.json`
- `docs/evidence/company_os_supervised_burnin/execution/receipts/wo-req-attempts-remaining-null-safe-9c9ba66627bb/000001.json`
- `docs/evidence/company_os_supervised_burnin/execution/authorities/wo-req-attempts-remaining-null-safe-9c9ba66627bb/000001.json`
- `docs/evidence/company_os_supervised_burnin/execution/efficiency/wo-req-attempts-remaining-null-safe-9c9ba66627bb/000001.json`
- `docs/evidence/company_os_supervised_burnin/resource_usage/wo-req-attempts-remaining-null-safe-9c9ba66627bb/000001.json`
- Raw runner state and session transcripts (outside this repository, as with Job A):
  `C:\Users\mgial\OneDrive\Documents\projects\company-os-supervised-burnin-runner-state\runs\wo-req-attempts-remaining-null-safe-9c9ba66627bb\run-000001\`
- Implementation branch: `eng-attempts-remaining-null-safe` @
  `532ce7a31ece35a48c5aed8cf61ce83976ab1b03` (pushed, remote-verified, **not merged
  anywhere** — not into this burn-in branch, not into `company-os-v1-bootstrap`, not into
  `main`)

## G. CEO decision gate

This job reached reviewer `PASS`, deterministic QA `PASS`, and integration gate `READY`.
Per the CEO's own instruction, the run stops here. It does not approve, does not merge, and
does not resume Jobs B or C. The next CEO decision determines whether to (A) approve this
corrected implementation for the supervised burn-in lineage, and (B) resume the remaining
burn-in jobs.
