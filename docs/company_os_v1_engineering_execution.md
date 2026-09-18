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
