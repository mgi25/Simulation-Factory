# The first real Company OS engineering dogfood

**Date:** 2026-09-19
**Branch:** `company-os-v1-first-real-dogfood`, based on `company-os-v1-read-efficiency-v3a` @ `ba851fa`
**Authorization:** one supervised, single-attempt, one-provider, one-session, one-reviewer-pass work order. Autonomous Company OS engineering remains PAUSED and was not touched.

This is the first Company OS engineering job run against real engineering work rather than a
benchmark fixture. Everything below is `mode: "real"` in the runtime's own telemetry.

---

## 1. Ancestry

The validated research chain is strictly linear from the canonical baseline, with no merges:

```
01a1638  company-os-v1-bootstrap              (canonical baseline)
  5d73557  eng-ai-resource-efficiency-v2-operational
    4b6064d  company-os-v1-consumer-resource-mode
      9b5f224  company-os-v1-repository-exploration-efficiency
        6dd7891  company-os-v1-repository-exploration-efficiency-v2
          ba851fa  company-os-v1-read-efficiency-v3a
```

13 commits, 0 merges in `01a1638..ba851fa`; each ref is an ancestor of the next.

One ref named in the brief is **not** in the chain, correctly: `eng-ai-resource-efficiency-v2 @ 5c1c035`
is the attempt-1 runner output that the AFTER-validation review returned as `changes_required`.
The work was redone on `eng-ai-resource-efficiency-v2-operational @ 5d73557`, which branches from
`01a1638` independently and **is** in the chain. Nothing was cherry-picked, rebased or reconstructed.

Baseline test suite at `ba851fa`, before any modification:
**6 failed, 4623 passed, 337 skipped** — the known gitignored-artifact / Godot-render failures in
`test_neon_proof.py`, `test_sloped_v251_world.py` and `test_sloped_v252_world.py`. No Company OS
suite fails at baseline.

---

## 2. The CLI write-scope gap does not exist on this branch

The brief asked for a fix to `python -m company.runtime packet`, which was diagnosed on
2026-09-16 as unable to produce a write-scoped packet because it had no way to supply an
`employee_contract`.

**That diagnosis was correct when it was made and is now stale.** The gap was real at
`be654e06` and at `company-os-v1-dogfood-research-capsule` — `grep -c "authority-override-file"`
returns 0 at both. It was closed by `a523d38` (*company-os: expose audited execution transport*),
which is an ancestor of the canonical baseline and therefore of this branch.

The working interface is `--authority-override-file`, and it is a **stronger** convention than the
`--employee-contract <path>` the brief proposed:

- it accepts only the five authority fields (`may_read`, `may_write`, `may_not_read`,
  `may_not_modify`, `autonomy_level`) and refuses anything else, so it cannot forge an
  `employee_id` or a capability list;
- everything else comes from `contract_from_registry`, so there is one definition of who the
  employee is;
- the resulting grant is recorded as `AuthoritySource.TEMPORARY_TASK_OVERRIDE`, never as the
  canonical contract.

Adding `--employee-contract` would have duplicated authorization logic, which the brief forbade.
**No CLI code change was warranted.**

There is no authority *ceiling* above the override, and that is by design, not an oversight:
neither `org_registry.yaml` nor `permissions.yaml` grants any employee a `may_write` path, so
`contract_from_registry` always produces an empty `may_write` and `_assert_scope_within_contract`
reads empty as "grants nothing". The override **is** the grant, and the fingerprinted authority
snapshot is what makes it auditable.

### What was actually wrong

Discoverability, and nothing else:

- no test anywhere passed `--allow` to the CLI, so the write-scope path was entirely uncovered;
- the argument's help text described only what it refuses.

A correct system therefore read as broken, and a previous session built a dogfood packet in
Python to work around a gap that was not there.

**Fix (commit `733b21e`):** the help text now names the grant, and seven focused tests pin the
path in both directions — the read-only packet when the argument is omitted; the bounded write
scope and its persisted authority snapshot when it is supplied; the two refusals (outside
`may_write`, reaching `may_not_modify`); a non-authority field; an absent file; and the expansion
commands still refusing the argument. No behaviour changed.

---

## 3. The work order

The originally prepared packet `c94edb3a7a72819a` (*dogfood-research-capsule-split*) is stale on
the merits, not merely because of the branch change: `09d837f` (*company-os: split research
knowledge capsules*) is an ancestor of `ba851fa`. The split is already done and the seed count is
19, not the 8 the task assumed. A replacement task of equivalent size was chosen.

| | |
|---|---|
| **Work order** | `wo-req-packet-authority-echo` (`9fced136fae4227d`) |
| **Request** | `req-packet-authority-echo` (`98404f9deb12bf44`) |
| **Objective** | `packet` prints the authority fingerprint and source only when a state directory is supplied. Without one it prints a packet that may already carry a writable path, with nothing identifying the grant behind it. Print the same fingerprint and source in that case too, computed from the contract already in hand and persisted nowhere. |
| **Risk / reversible** | LOW / yes |
| **Capsule** | `company-runtime`, matched by path — *"owns company/runtime for task path company/runtime"* |
| **Authorized paths** | `company/efficiency`, `company/runtime`, `tests/test_company_context_assembly.py`, `tests/test_company_efficiency.py`, `tests/test_company_runtime.py` |
| **Forbidden paths** | `ai_platform`, `company/constitution.md`, `knowledge`, plus the ten protected governance files |
| **Specialist domain** | none — *"the objective names no security, governance, architecture or concurrency work and the risk is not high, so this is routine implementation"* |
| **Reasoning class** | C, ceiling D |
| **Model tier** | **standard** |

Scope derivation is retrieval, not invention: the CEO named no files. Note that
`tests/test_company_execution_transport.py` is **not** in the authorized set, because the
`company-runtime` capsule does not declare it — so the dogfood's own test had to go in
`tests/test_company_runtime.py`. The bounding worked exactly as designed.

### Authority granted

`ExecutionAuthoritySnapshot` `9cf0eafdf15c4e77`, source `temporary_task_override`,
`no_subagents: true`, recorded at
`execution/authorities/wo-req-packet-authority-echo-f222300f6c18/000001.json`.
`may_write` is the five authorized paths; `may_not_modify` is the twelve forbidden ones.

This is the CLI write-scope path of §2, driven by `company.engineering` rather than by hand.

### Resource profile

`consumer`: one provider, one parallel session, **one developer attempt**, one reviewer pass,
`auto_continue_after_changes_required: false`, context budget 16000 chars, ref ceiling 8,
`strongest_requires_escalation: true`. The packet carried 4 context refs and 1985 chars.

The runtime states its own limits plainly: *"Company OS does not start a process and therefore
enforces nothing inside a session. What it can do is refuse to issue the next one."*

---

## 4. What the developer did

Commit `3997a8e`, three files, all inside the authorized set:

- `company/runtime/session_adapter.py` — `ManualExternalSessionAdapter.prepare`'s snapshot
  construction moved verbatim into a module-level `authority_for(plan, packet, *, packet_attempt,
  employee_contract)`. One definition now decides which `AuthoritySource` a contract came from.
- `company/runtime/execution_cli.py` — `_packet` calls the same function with attempt 1 when
  there is no outbox, printing `{"record_ref": null, "fingerprint": …, "source": …}`. The
  `--state-dir` branch is untouched.
- `tests/test_company_runtime.py` — two tests: the read-only packet names its canonical contract
  and writes nothing; a write-scoped packet prints the same authority fingerprint with and
  without an outbox.

Tests, run individually: `test_company_context_assembly.py` 9 passed,
`test_company_efficiency.py` 67 passed, `test_company_runtime.py` 22 passed (2 new).
Adjacent suites over the same boundary: 190 passed.

---

## 5. What the reviewer found

Reviewer `chief_architect`, routed by `software_architecture` — disjoint from the implementer's
`software_implementation`, on a read-only packet with an empty path scope.

Attested **pass**, all four acceptance criteria satisfied, with two advisory findings:

1. `find-attempt-one-assumed` — the un-persisted snapshot hardcodes `packet_attempt` 1, so its
   fingerprint equals a recorded one only for a first attempt into a fresh outbox. The null
   `record_ref` bounds the harm; the limitation is disclosed, not enforced.
2. `find-helper-not-exported` — `authority_for` is a new public name not re-exported from
   `company/runtime/__init__.py`, unlike the adapter beside it.

**Deterministic QA disagreed, and won.** Worst verdict wins, so the adjudicated outcome is
`changes_required`:

```
attested_outcome      = pass
deterministic_outcome = changes_required
outcome               = changes_required
```

The two deterministic findings (`receipt-01`, `tests-not-reported`) are the same defect: the
first receipt reported the three required suites as **one combined pytest command**, and the
validator requires each required test to be reported individually.

---

## 6. The finding that matters: one attempt, spent on an evidence format

The first receipt was refused with `required test(s) not reported: …`. That refusal is correct —
a combined command is not evidence that each required suite passed. But refusing it **moved the
job from `developing` to `testing` and consumed the single authorized developer attempt**:

```
developing -> testing : "attempt 1 recorded rejected: required test(s) not reported: …"
developer_attempts    : 1
corrections_remaining : 0
```

A corrected receipt — same commit, same code, the three suites simply re-run individually — could
not then be ingested:

```
$ python -m company.engineering receipt …
a developer receipt is ingested from developing, not from testing
```

So an **operator formatting error in the evidence is indistinguishable, to the attempt budget,
from a failed implementation.** The code was correct and the suites all passed; the job still
carries a rejected attempt and a `changes_required` review because of how the pytest invocation
was written down.

This is the single most useful thing this run produced, and it is a design question for the CEO,
not a bug to patch inside this work order: should receipt *validation* failures that do not touch
the implementation consume a developer attempt, or should the receipt be correctable in place
while the attempt stays open?

---

## 7. The gate

The gate was run from its own CLI against real suite evidence — all eleven required Company OS
suites executed and passed (`docs/evidence/.../inputs/suites_evidence.json`).

```
report_id                         integration-readiness-2026-09-19-889f493dcc42cf24
required checks                   34 / 34 pass
advisory                          1 fail, 3 unknown
authorizes_production_integration false
```

The one failing advisory, `architecture.subsystem_ownership_bounded` (7 modules under
`company/workforce` and `knowledge` claimed by no capsule), is pre-existing and untouched by this
change.

**Company OS refused to record the report**, correctly:

```
$ python -m company.engineering gate …
a gate verdict is recorded from gate, not from decision_required. The gate runs after review passes.
```

Review did not pass, so the gate stage is closed. The report exists as evidence; the job does not
claim it.

---

## 8. Where it stopped

```
STATUS
  DECISION_REQUIRED

DECISIONS REQUIRED
  - the work order's 1 authorized developer attempt(s) are spent and the review still
    requires changes; continuing needs either additional-attempt authorization on this
    work order or a new one

CEO OPTIONS
  [APPROVE]  [REQUEST CHANGES]  [REJECT]
  READY FOR CEO APPROVAL is a request to be read, not an approval. Nothing here merges,
  deploys or publishes, and Company OS holds no capability to.
```

No decision was recorded. No merge, no push to any canonical branch, no deployment, no publishing.

The runtime did not retry, did not auto-continue after `changes_required`, did not create a
second work order, did not escalate to a specialist, and did not request automatic remediation.
Every stop in this run was the runtime's own, reached without intervention.

There was no global autonomous-pause flag to lift. The boundaries that bound this run —
`max_developer_attempts: 1` and the consumer profile's `auto_continue_after_changes_required:
false` — are per-work-order and per-profile. No standing state was changed.

---

## 9. Telemetry

`execution/efficiency/…/000001.json`, `mode: "real"`:

| | |
|---|---|
| provider / model | `anthropic` / `claude-opus-5` |
| capsules selected | 1 (`company-runtime`), 2761 chars |
| context manifest | 1919 chars, fingerprint `7a5756a23d530ab1` |
| execution packet | 3605 chars |
| context expansions | 0 requested, 0 approved, 0 denied |
| estimated tokens | 1009 (`ceil(utf8_bytes/4)`, source `estimated`) |
| **real tokens** | **`unavailable` — "provider omitted token usage"** |
| **cost** | **`unavailable` — "provider omitted monetary cost"** |
| repository files read | `[]` |
| tool activity | `[]` |
| subagents used | 0 |
| retries | 0 |
| graphify / rtk | not installed |

The honest gap: this was an interactive Claude Code session, not a runner-driven `stream-json`
session, so no provider usage envelope was captured. The receipt declares eight metrics as
`unreliable_metrics` and gives `usage_source` a reason string rather than a number. Nothing was
fabricated, and `company.efficiency.budget.check_budget` will refuse to score the unavailable
dimensions.

**Consequence: a supervised interactive dogfood cannot produce cost or token telemetry.** Only a
runner-driven session can. That is a real limit on what supervised runs can tell us about
resource efficiency, and it should be stated before the next one rather than discovered after.

---

## 10. Assessment

| Question | Answer |
|---|---|
| Did CLI write-scope plumbing work? | Yes — it already worked; it was untested and undocumented. Now covered by 7 tests. |
| Did deterministic intake/routing work? | Yes. Capsule matched by path, scope derived from `owns_paths`, specialist correctly none, tier standard. |
| Did employee contract / authority bounding work? | Yes. Fingerprinted `temporary_task_override`, `may_write` exactly the authorized paths, diff stayed inside them. |
| Did consumer-resource-mode work? | Yes. One provider, one session, one attempt, one reviewer pass, no escalation, no subagents, no retries. |
| Did the developer complete the task? | Yes. Three files, all four acceptance criteria met. |
| Did tests validate it? | Yes. All required suites pass individually; 2 new tests; no regression in 4623-test baseline. |
| Did the reviewer evaluate correctly? | Yes, and deterministic QA overrode the human verdict on evidence the reviewer had discounted. Worst verdict won. |
| Did the integration gate behave correctly? | Yes — 34/34 required pass, and it refused to record a verdict for a job whose review had not passed. |
| Did the system stop at CEO approval? | Yes. `decision_required`, no decision recorded, nothing merged. |
| Any hidden manual workaround? | No. Two runtime refusals were hit and neither was bypassed. The receipt was corrected once, in format only, and the runtime refused the corrected version too — which is recorded, not worked around. |
| Any resource/telemetry issue? | Yes, one: no real token or cost telemetry from an interactive session. Declared as unavailable, not estimated over. |

**Recommendation: READY FOR ANOTHER SUPERVISED REAL JOB**, with two conditions carried forward:

1. **Report every required test as its own receipt entry.** Until the attempt-accounting question
   in §6 is decided, a combined pytest command costs the whole work order.
2. **Run the next one through the external engineering runner**, not interactively, if resource
   telemetry is wanted at all.

This is not yet evidence sufficient to lift the autonomous-engineering pause. One supervised job
that stopped correctly shows the stops work under supervision; it says nothing about what happens
when nobody is watching, and the one unforced error in this run — a receipt format — was made by
the supervisor. A second supervised job under the runner, with real telemetry and a clean
attempt, would be the evidence to bring to that separate CEO decision.

---

## Evidence

Every record below is under `docs/evidence/company_os_first_real_dogfood/`.

| Artifact | Path |
|---|---|
| CEO result page | `ceo_result_page.txt` |
| Intake assessment | `intake_assessment.json` |
| Developer brief | `developer_brief.json` |
| Reviewer brief | `reviewer_brief.json` |
| Integration gate report | `integration_gate_report.json` |
| Work order | `state/engineering/work_orders/…/000001.json` |
| Job transitions (5) | `state/engineering/jobs/…/00000{1..5}.json` |
| Plan | `state/engineering/plans/…/000001.json` |
| Attestation | `state/engineering/attestations/…/000001.json` |
| Adjudicated review | `state/engineering/reviews/…/000001.json` |
| Result | `state/engineering/results/…/000001.json` |
| Developer packet | `state/execution/packets/…-f222300f6c18/000001.json` |
| Reviewer packet | `state/execution/packets/…-review-495d61bbb23c/000001.json` |
| Authority snapshots | `state/execution/authorities/…/000001.json` (both) |
| Receipt | `state/execution/receipts/…/000001.json` |
| Efficiency telemetry | `state/execution/efficiency/…/000001.json` |
| Resource usage | `state/resource_usage/…/000001.json` |
| Operator inputs | `inputs/{request,receipt,attestation,suites_evidence}.json` |
