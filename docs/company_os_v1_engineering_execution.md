# Company Engineering Execution Loop v1

    CEO request -> work order -> developer -> review -> gate -> CEO result

Base: `company-os-v1-youtube-connectivity` at `324539cee8a3c947f0f83f4ce000dbe1eab10879`.
Branch: `company-os-v1-engineering-execution`. Nothing is merged.

## 1. Architecture audit, performed before any code was written

The audit read the whole control plane: `company/runtime/`, `company/integration/`,
`company/dashboard/`, `company/workforce/`, `ai_platform/`, `knowledge/company_os/`
and the four bootstrap YAML contracts. The finding that shaped every later
decision is in §3.

| Stage | Verdict before this task | What already carried it |
|---|---|---|
| CEO request intake | **MISSING** | nothing: no contract, no CLI, no record for "Build X" |
| Engineering work order | **PARTIAL** | `TaskSpecification` (objective, capabilities, context, ceiling) and `SessionPacket` (scope, branch, tests, criteria) between them hold most of the *fields* — but per attempt, with no durable identity, no requester, no status, no retry bound and no review/gate/result links |
| Planner / decomposition | **PARTIAL** | `plan_task` classifies and routes deterministically (`ai_platform.resource_classes.classify`, `company.runtime.routing.match_capabilities`). There is no stage decomposition and no DECISION-REQUIRED stop |
| Developer capability | **PARTIAL** | the *boundary* exists (`ManualExternalSessionAdapter`); the *employee* did not. `org_registry.yaml` had no implementation capability at all: engineering held `software_architecture`, `dependency_governance`, `technology_migration`, `simulation`, `physics`, `fairness`, `benchmarks` and nothing that writes code |
| Tool / repository / code / test execution | **EXISTS, EXTERNAL BY CONTRACT** | see §3 — the gate forbids Company OS from spawning a process, so execution is an external session with a signed receipt |
| Execution receipts | **EXISTS** | `SessionReceipt`, `validate_receipt`, `ExecutionStore` (append-only, `O_EXCL`), `ExecutionAuthoritySnapshot`, `ResourceUsageRecord` |
| Engineering review / code QA | **MISSING** | `company/org_intelligence/review.py` is an *organizational* review over a window (roles, capabilities). Nothing reviewed a diff, a test run or an acceptance criterion |
| Integration gate | **EXISTS** | `company/integration/` — 37 checks, required/advisory split, `READY` / `BLOCKED` / `INSUFFICIENT_EVIDENCE`, `authorizes_production_integration = False` in every report it can build |
| Approvals / decision records | **PARTIAL** | `CEODecisionItem` is a read-only dashboard projection; `knowledge/company_os/records/decision/` stores decisions. No engineering approval record and no place to put one |
| CEO dashboard / brief | **EXISTS, READ-ONLY** | `build_snapshot` + `build_brief`. Its README states it "does not approve, reject, spend, hire, archive, publish, merge, repair, or schedule anything", and the gate check `executive.dashboard_cannot_approve` enforces that. There was **no request boundary**: the CEO could read the company and not ask it for anything |
| Workflow state | **MISSING** for engineering | `LifecycleState` covers one *attempt* (specified → prepared → recorded). `ResearchStage` is the state-machine idiom, for research threads |
| Authorization | **EXISTS** | employee contract → `authority_projection` → `ExecutionAuthoritySnapshot` (fingerprinted, immutable, per packet attempt); `PathScope` (forbidden wins, empty allow-list allows nothing); `build_session_packet` refuses a scope the contract does not already grant |
| Context selection / expansion | **EXISTS** | `assemble_context` + `CapsuleIndex` + `ContextExpansionLedger`, all reference-only |

### The smallest missing bridge

Five things, and only five, stopped a CEO engineering request travelling end to end:

1. **No intake.** No contract turned an objective into a bounded, authorized request.
2. **No durable work order.** Authority existed per attempt and died with it.
3. **No implementer.** No employee could be routed work that writes code.
4. **No code review.** The implementation could only be checked by the thing that produced it.
5. **No CEO result.** The gate, the tests and the receipt were four unrelated records.

Everything else was reused unchanged.

## 2. What was NOT built, deliberately

No new agent framework, planner framework, memory system, context system, tool
framework or gate framework. In particular:

- **`company/runtime/` is untouched.** Packets, receipts, authority snapshots,
  the execution store, context expansion and usage records are consumed exactly
  as they are. `ManualExternalSessionAdapter.prepare(..., employee_contract=)`
  and `.ingest(...)` are the only entry points used.
- **`company/integration/` is byte-identical to the base commit.** The gate is
  not extended, re-weighted, or re-implemented, and `company/engineering` cannot
  import it (§4). Engineering *reads a gate report it did not produce*.
- Routing is `match_capabilities`. Classification is `classify`. Context is
  `assemble_context`. Path enforcement is `PathScope`. Append-only writing is
  `company.runtime.state_paths`.

## 3. The finding that decides the honesty of the whole loop

`company/integration/policy.py` marks `production.no_publishing_capability`
**required**, and `company/integration/boundary.py` implements it as: no Company
OS module may import `subprocess`, `multiprocessing` or `pty`, or call
`os.system`, `os.popen`, `os.fork`, `os.exec*`, `os.spawn*` or `os.posix_spawn`.

The consequence is structural, not incidental:

> **Company OS cannot run pytest, cannot run git, and cannot launch Claude Code
> or Codex.** Not "has not yet been wired to" — *may not*, and a version that
> did would fail its own required gate check.

So this milestone does not pretend to autonomy it cannot have. The developer and
the reviewer are **independent top-level sessions started by a human**, which is
also what constitution rule 3 and `ai_platform/policy.py` already require. What
Company OS does deterministically is everything else: intake, authorization,
scope derivation, context bounding, packet construction, receipt validation,
protected-surface verification, review adjudication, gate-evidence custody,
result assembly and the approval boundary.

`company/engineering/README.md` restates this at the top of the package, and
`docs/company_os_v1_engineering_execution.md` §8 lists every remaining manual
step.

## 4. Why `company/engineering` may not import the gate

The existing subsystem import graph already contains
`company/integration -> company/dashboard`. The dashboard must show the
engineering lifecycle (§11 of the brief), so `company/dashboard -> company/engineering`
is a new edge. Had engineering also imported the gate, the graph would have held

    company/integration -> company/dashboard -> company/engineering -> company/integration

— a cycle, and `architecture.no_subsystem_import_cycle` is a **required** check.

The resolution is the better design anyway. The gate is run by its own unmodified
CLI and its JSON report is handed to engineering as *supplied evidence*, exactly
as `SuiteEvidence` is handed to the gate. `GateVerdict.from_report_mapping` parses
a report; it cannot compute one. **Engineering therefore cannot fabricate a gate
pass, because it holds no code that can produce a verdict.**

## 5. The real path, module by module

```
CEO writes a CEORequest                              company/engineering/intake.py
  -> screen_reserved + screen_credentials            intake.py         DETERMINISTIC
  -> select_capsules over the capsule index          knowledge/.../select.py
  -> ProtectedSurface.capture (10 files digested)    protected.py      DETERMINISTIC
  -> EngineeringWorkOrder                            work_order.py     THE CEILING
  -> derive_plan (7 stages)                          plan.py           DETERMINISTIC
  -> EngineeringJob.open -> planning                 lifecycle.py

  -> plan_task (classify + route)                    company/runtime/lifecycle.py
  -> employee_contract: may_write = authorized paths work_order.py
  -> build_session_packet re-reads that contract     company/runtime/packets.py
  -> ExecutionAuthoritySnapshot (fingerprinted)      company/runtime/authority.py
  -> SessionPacket + SessionTransportBundle          transport.py      -> OUT

     [ an external session a human starts implements, tests, commits, pushes ]

  <- SessionReceipt                                                    <- IN
  -> validate_receipt + repository_findings          company/runtime/receipts.py
  -> ResourceUsageRecord + HandoffArtifact           company/runtime/attempts.py
  -> job -> testing                                  orchestrator.py

  -> review_specification routes to a DIFFERENT      work_order.py
     employee; reviewer_contract is read-only
  -> a second SessionPacket                          transport.py      -> OUT

     [ a second external session reviews the diff ]

  <- ReviewerAttestation                                               <- IN
  -> deterministic_findings: protected surface       review.py         DETERMINISTIC
     re-read, path scope, tests, criteria, merge
  -> adjudicate: worst_of(attested, deterministic)   review.py
  -> job -> gate | planning | decision_required | blocked

     [ a human runs pytest; a human runs the gate's own CLI ]

  <- GateVerdict.from_report_path                    gate_evidence.py  <- IN
  -> readiness_from re-derives the verdict           gate_evidence.py  DETERMINISTIC
  -> stale_against(implementation_commit)            gate_evidence.py
  -> job -> ready_for_approval | blocked

  -> EngineeringResult.build + render_text           result.py         DETERMINISTIC
  -> EngineeringStore.append_result                  store.py
  -> CompanyStatePaths -> engineering section        company/dashboard/builder.py
  -> CEODecisionItem -> CEO brief                    company/dashboard/brief.py

     [ the CEO reads it and decides ]

  <- CEODecision                                     decision.py       <- IN
  -> job -> closed. Nothing is merged.
```

## 6. Governance, as checks rather than claims

| Property | Where it is enforced | Test |
|---|---|---|
| The work order cannot change | `fingerprint()` + `assert_unchanged` at every stage; `put_work_order` refuses a differing record | `test_the_work_order_is_immutable_once_authorized` |
| A plan cannot widen the ceiling | `ImplementationPlan.assert_within` | `test_a_plan_cannot_propose_writing_outside_the_work_order` |
| A receipt cannot grant anything | `from_mapping` refuses unknown fields | `test_a_receipt_cannot_arrive_with_a_field_that_grants_anything` |
| An attestation cannot grant anything | the same, and it cannot claim a deterministic finding | `test_an_attestation_cannot_arrive_with_a_field_that_grants_anything` |
| Work stays inside scope | `PathScope` on the packet, re-checked against the receipt | `test_a_receipt_reporting_an_out_of_scope_change_is_rejected` |
| Protected policy cannot be weakened | `ProtectedSurface` digested before, re-read after | `test_a_protected_change_escalates_to_the_ceo_rather_than_a_retry` |
| The implementer cannot review itself | disjoint capabilities, plus `SelfApproval` on identity | `test_the_implementer_cannot_review_its_own_work` |
| A reviewer PASS cannot rescue a failed check | `outcome = worst_of(attested, deterministic)` | `test_a_reviewer_pass_cannot_rescue_a_failed_deterministic_check` |
| The gate cannot be forged | engineering holds no code that computes readiness | `test_engineering_imports_neither_the_gate_nor_the_dashboard` |
| A stale gate report is not evidence | `stale_against(implementation_commit)` | `test_a_gate_verdict_from_another_commit_does_not_describe_this_work` |
| The correction loop is bounded | `max_developer_attempts`; only `planning -> developing` spends one | `test_the_correction_loop_is_bounded_by_the_work_order` |
| Nothing is approved or merged | no such state exists; `authorizes_merge` is always False | `test_a_successful_workflow_does_not_merge` |
| A decision names a person | `assert_named_person` | `test_a_decision_must_name_a_person_and_not_the_system` |
| No publish or process capability | an AST walk over the package | `test_no_publishing_or_process_capability_is_introduced` |
| No credential is read | an AST walk for `environ` / `getenv` | `test_no_credential_is_read_by_this_package` |
| YouTube is untouched | no import, no mention | `test_the_youtube_subsystem_is_untouched_by_this_milestone` |
| The CEO view cannot act | no verb on the dashboard surface | `test_the_dashboard_projection_cannot_act_on_a_work_order` |

## 7. The dogfood run

One real CEO objective, carried end to end. Every record is in
`docs/validation/company_os_engineering_execution/`.

| Stage | Result |
|---|---|
| CEO objective | "Let me check at any time whether the protected governance files have changed since an engineering work order was authorized, without having to run a review to find out." |
| work order | `wo-governance-drift-check`, fingerprint `6c1ce3643e5b86fc` |
| derived scope | `company/engineering`, `tests/test_company_engineering_execution.py` — the CEO named no file |
| derived criteria | 8, from the owning capsule's objective, invariants and declared test |
| protected surface | 10 files digested at authorization |
| packet | `2151d8654cee3405`, attempt 1, 2740 chars, to `software_implementation_engineer` |
| authority | `26369f8aec216a4a`, `may_write` exactly the two authorized paths |
| implementation | `company/engineering/verify.py` plus its CLI command and 8 tests — 4 files, 422 insertions |
| commit | `d59a5d918630f763d0e93997626636e72a4dedc3` on `eng-governance-drift-check`, pushed, remote SHA verified against the real refs |
| targeted tests | `tests/test_company_engineering_execution.py` — 92 passed |
| affected suites | `tests/ -k company` — 1579 passed |
| review | PASS by `chief_architect`; 3 advisory findings; 8/8 criteria answered with an evidence reference each |
| gate | READY, `integration-readiness-2026-09-18-06cb98f671e8255c`, 34 required checks pass, 0 blockers |
| final state | **ready_for_approval**, and not merged |

The three review findings were real rather than decorative: `__all__` ordering
inside the class group, a `to_dict()`/`fingerprint()` pair with no
`from_mapping` to read one back, and an absolute filesystem path on an exported
record. None blocking, all recorded on the CEO page.

## 8. Every step that still needs a human

1. **The developer session.** A human runs Claude Code or Codex against the
   packet. Nothing here can launch one.
2. **The review session.** The same, for the reviewer packet. In the dogfood
   run above, both stages were performed by **one** Claude Code session
   sequentially. The *employees* were distinct, the packets were distinct, and
   the separation-of-duties refusal is real and enforced — but the model behind
   both was the same one. A genuinely independent review needs a second
   human-started session.
3. **Running pytest.** The gate holds no process-spawn authority and neither
   does this package. A human runs the suites and writes the results into a
   suite-evidence file.
4. **Running the integration gate.** `python -m company.integration check
   --json`. Engineering reads that report; it cannot produce one.
5. **Writing the receipt and the attestation.** Both are JSON returned by the
   external session. A session that returns nothing leaves its packet attempt
   with no receipt, which the dashboard reports as a blocked pending attempt.
6. **The approval decision, and any integration that follows it.** The CEO
   decides; the merge happens outside Company OS, by hand.

Everything else — intake, scope derivation, authorization, packet
construction, receipt validation, protected-surface verification, review
adjudication, gate custody, result assembly, the state machine and the
dashboard projection — is deterministic code in this repository.

## 9. Not autonomous, and the word is chosen

This is a **governed, evidence-carrying engineering workflow with two
model-executed stages**. It is not autonomous, and neither this document nor
the package calls it that. Three of its stages need a human to start a session
or run a command. `company/engineering/README.md` carries the same table at the
top of the package, so the next reader meets the boundary before the code.
