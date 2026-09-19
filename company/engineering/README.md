# Company engineering execution loop

```
CEO request -> work order -> developer -> review -> gate -> CEO result
```

One CEO objective travels from a sentence to a page the CEO can approve. This
package is the deterministic part of that journey and nothing else.

## Read this first: what is automatic, and what is not

`company/integration/policy.py` makes `production.no_publishing_capability` a
**required** gate check, and `company/integration/boundary.py` implements it as:
no Company OS module may import `subprocess`, `multiprocessing` or `pty`, or
call `os.system`, `os.popen`, `os.fork`, `os.exec*`, `os.spawn*` or
`os.posix_spawn`.

So, plainly:

> **Company OS cannot run pytest, cannot run git, and cannot launch Claude Code
> or Codex.** Not "has not been wired to yet" — *may not*, and a version that
> did would fail its own required gate check.

| Stage | Who does it |
|---|---|
| intake, scope derivation, work order | **deterministic code**, here |
| plan derivation | **deterministic code**, here |
| packet construction, authority snapshot | **deterministic code** (`company.runtime`) |
| **implementation** | **an external session a human starts** |
| receipt validation, path scope, git-evidence shape | **deterministic code** |
| protected-surface verification | **deterministic code**, here |
| **review judgment** | **an external session a human starts** |
| review adjudication, severity combination | **deterministic code**, here |
| running the test suites | **a human runs pytest**; results are supplied |
| running the integration gate | **the gate's own CLI**; its report is supplied |
| result assembly, readiness derivation | **deterministic code**, here |
| **the approval decision** | **the CEO**, recorded and never acted on |

Three stages need a human or a model. Everything between them is code that
raises rather than warns.

## The modules

| Module | Holds |
|---|---|
| `intake` | a CEO objective -> a bounded work order, or DECISION REQUIRED |
| `work_order` | the authority ceiling: immutable, fingerprinted, derived from |
| `protected` | the governance files, digested before the work and re-read after |
| `plan` | a proposal about method, refused if it widens the ceiling |
| `lifecycle` | the job state machine and the bounded correction loop |
| `review` | deterministic QA plus one independent reviewer; worst verdict wins |
| `gate_evidence` | the gate's verdict, read and never computed here |
| `result` | the one page the CEO reads |
| `decision` | APPROVE / REQUEST_CHANGES / REJECT, recorded and not acted on |
| `store` | the append-only history under a caller-supplied directory |
| `transport` | the compact payload an external session receives |
| `orchestrator` | one function per stage, each one a recorded move |

## Where the scope comes from

The CEO names no files. Every Company OS subsystem already has a capsule
declaring `owns_paths`, `must_not_modify` and `tests`, so intake matches the
objective against the capsule index and reads the scope out of the capsule that
owns the subject:

```
"check whether the governance files changed since a work order was authorized"
  -> subsystem_hint company/engineering
  -> capsule company-engineering-execution
  -> authorized_paths  company/engineering
  -> forbidden_paths   its must_not_modify
  -> required_tests    tests/test_company_engineering_execution.py
```

That is retrieval, not invention (constitution rule 4). A subject no capsule
owns produces DECISION REQUIRED with the capsule list as options, rather than a
guess.

## The five refusals

1. **A work order cannot be changed.** `fingerprint()` is the proof, every
   stage compares it, and `put_work_order` refuses a differing record under an
   existing id.
2. **A plan cannot widen the ceiling.** `assert_within` checks every writing
   step against the work order's scope.
3. **The implementer cannot review itself.** Implementation and review route by
   disjoint capabilities (`software_implementation` / `software_architecture`),
   a work order whose review capability is also an implementation capability is
   refused at construction, and `adjudicate` raises `SelfApproval` on identity.
4. **Protected policy cannot be weakened.** `ProtectedSurface` digests the ten
   governance files at authorization and re-reads them at review. A changed
   digest is BLOCKED and escalates to the CEO, whatever the receipt said. This
   is the check that catches an edit the receipt does not mention.
5. **Nothing is approved and nothing is merged.** No state in `JobState` means
   approved; `closed` is reached only by a recorded `CEODecision`; and
   `authorizes_merge` is a field that is always `False` on both the decision and
   the result.

## From the command line

```
python -m company.engineering request      --request-file r.json --state-dir S --repo-root .
python -m company.engineering brief        --work-order WO --state-dir S
python -m company.engineering receipt      --work-order WO --receipt-file x.json --state-dir S
python -m company.engineering review-brief --work-order WO --implementer E --state-dir S
python -m company.engineering review       --work-order WO --attestation-file a.json --implementer E --state-dir S
python -m company.engineering gate         --work-order WO --gate-report g.json --state-dir S
python -m company.engineering result       --work-order WO --state-dir S
python -m company.engineering decide       --work-order WO --decision-file d.json --state-dir S
python -m company.engineering status       --work-order WO --state-dir S
python -m company.engineering list         --state-dir S
```

Exit code is the stage's answer: `0` advanced, `1` stopped on evidence, `2`
refused. `--state-dir` is never defaulted.

The gate report is produced by the gate, not by this package:

```
python -m company.integration check --repo-root . --json --suite-evidence suites.json > gate.json
```

## Dependency direction

```
ai_platform <- knowledge.company_os <- company.runtime <- company.engineering
                                                              ^
                                                     company.dashboard
```

Nothing here imports `company.integration` or `company.dashboard`.
`gate_evidence.py` explains why: `company/integration` already imports
`company/dashboard`, so an edge to the gate would close a subsystem cycle, and
`architecture.no_subsystem_import_cycle` is a required check. The consequence is
also the point — **this package holds no code that can produce a readiness
verdict, so it cannot produce a favourable one.**

## What is deliberately absent

No agent framework, planner framework, memory system, context system, tool
framework or gate framework. Routing is `match_capabilities`, classification is
`classify`, context is `assemble_context`, path enforcement is `PathScope`,
append-only writing is `company.runtime.state_paths`, and the whole external
execution boundary is `ManualExternalSessionAdapter`. `company/runtime/` and
`company/integration/` are unmodified by this milestone.
