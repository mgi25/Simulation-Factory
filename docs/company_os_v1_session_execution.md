# Handoff — Company OS v1, Phase 4 (external session execution boundary)

Branch: `company-os-v1-session-execution`, from the integrated Phase 3 head
`c106f53`.

## Objective

Company OS could already take a task from specification to
`execution_prepared`: classify it, route it, select an employee, and bound its
context to references. It could not hand that prepared task to a real,
independent top-level session and take the result back.

This phase builds that boundary — and only that boundary. It does not launch
Claude Code, Codex, an API, or any other agent. It produces a compact packet a
session can be given, and validates and records what comes back.

```
TaskPlan → SessionPacket → (an independent top-level session) → SessionReceipt
         → validation → ResourceUsageRecord + HandoffArtifact → execution history
```

## What was built

| Module | Lines | Responsibility |
|---|---:|---|
| `company/runtime/packets.py` | 489 | `SessionPacket`, `ExecutorHint`, `build_session_packet` |
| `company/runtime/receipts.py` | 565 | `SessionReceipt`, `ReportedTest`, `validate_receipt` |
| `company/runtime/session_adapter.py` | 287 | `ManualExternalSessionAdapter` — prepare and ingest |
| `company/runtime/execution_store.py` | 228 | append-only packets/receipts, attempts by task |
| `company/runtime/git_evidence.py` | 184 | SHA/branch shape; offline ref reading |
| `company/runtime/path_scope.py` | 140 | `PathScope` — allowed/forbidden prefix rules |
| `company/runtime/state_paths.py` | 94 | the one exclusive-create append primitive |

`usage_store.py` was refactored onto `state_paths.py` so there is a single
append-only write in the runtime rather than two copies of it. Its file layout,
pointers and behaviour are unchanged; the existing tests prove it.

## The decisions worth keeping

**The executor hint is outside the packet fingerprint.** A packet may say
`claude_code`, `codex`, `human` or `future_adapter`. Nothing reads it, and
`fingerprint()` is computed over the packet *without* it — so the same work
prepared for two tools has one identity, and a receipt from either answers the
same packet. Had the hint entered the fingerprint, changing who runs a task
would silently have made it a different task. This is the concrete form of
provider independence: not "we avoided importing an SDK", but "the vendor name
cannot reach the identity of the work".

**An empty allow-list allows nothing.** A packet naming no writable path is a
read-only packet, and a session reporting a change against one has exceeded its
scope. Silence is not permission — `permissions.yaml` grants authority by
naming it, and so does a packet. Forbidden rules win over allowed ones, so a
packet that allows `company/` and forbids `company/permissions.yaml` means the
file is out of bounds.

**A receipt cannot escalate authority, because there is no field it can arrive
in.** The realistic vector is not a forged value but an extra key —
`autonomy_level: 5`, `ceo_approved: true`, `production_authority: true` — left
in the hope that some later reader honours it. `SessionReceipt.from_mapping`
refuses any key the schema does not name, the way `ExecutionPolicy.from_mapping`
refuses an unknown policy key. Validation then compares the receipt with the
packet, never the reverse. A CEO-reserved task is refused a packet outright: it
escalates to the CEO rather than being transported to a worker.

**A packet's path scope is checked against the employee contract.** An allowed
path outside `may_write`, or inside `may_not_modify`, fails at construction.
The transport layer cannot grant what the contract withholds.

The check is fail-closed on an empty contract, which is the case that matters
in Bootstrap Mode: `contract_from_registry` fills the schema template, and that
template's `may_write` is `[]`. An empty `may_write` therefore means *read-only*
- no writable path - rather than *unrestricted*. Every allowed path a packet
declares must sit inside at least one `may_write` rule, so the only packet a
default bootstrap contract can carry is one that declares no writable path at
all. Write authority is configured onto a contract, deliberately; it is never
acquired by a packet asking for it.

**The two treatments of the no-subagent rule are different on purpose.**
`no_subagents=false` is a *claim* that constitution rule 2 does not apply, and
construction refuses it — there is no such packet and no such receipt.
`subagents_used=1` is a *report of fact*: it must be constructible, or the one
receipt that proves a violation happened could not be written down. It fails
validation, ingestion refuses it, and the receipt file stays in the history as
the audit trail. `ai_platform/usage.py` already made this distinction; this
phase follows it.

The chain, proven end to end by
`test_the_no_subagent_rule_holds_at_every_link`:

```
org_registry.global_constraints.no_subagents = true
permissions.bootstrap_defaults.no_subagents  = true
agent contract        no_subagents = true
ExecutionPolicy       allows_nested_agents = False
ExecutionPreparation  no_subagents = True
SessionPacket         no_subagents = True
SessionReceipt        subagents_used = 0
ResourceUsageRecord   subagents_used = 0
```

**Git evidence is split between shape and substance.** Shape is always
checkable and always checked: a SHA looks like a Git object name, the branch
equals the packet's, `remote_branch_sha` equals the commit, `remote_verified`
is asserted rather than assumed, and `merge_performed` is fatal in any outcome.
Substance needs a clone, so `repository_findings()` reads `.git/refs` and
`packed-refs` directly — following the `gitdir:`/`commondir` indirection a
linked worktree uses — with no subprocess and no network. A verification step
that shells out behaves differently in CI; one that reaches the network cannot
run in a test. It is optional (`adapter.ingest(..., repo_dir=...)`), because
ingestion must also work on a machine that has never seen the repository.

**A failed receipt is recorded, not discarded.** Validation failure produces a
*rejected* attempt with the failures as its rejection reason — one canonical
usage record, one compact handoff — because a rejected attempt is the cost of
reaching an accepted one and belongs in the denominator of resources per
accepted deliverable. Attempt 001 rejected and attempt 002 accepted both stay,
in order, and `O_EXCL` rather than a check-then-write makes that a filesystem
guarantee rather than a convention.

## Measured

For a class-C task with 9 context references:

| | chars |
|---|---:|
| packet's own content (`size_chars`) | 1,179 |
| packet serialised as canonical JSON | 3,401 |
| control-plane source it points at | 89,953 |

A 26× ratio, achieved the same way the context manifest achieves it: every
pointer passes `assert_reference`, so a pasted function body is a construction
error rather than a large packet.

## State layout

```
<state_dir>/execution/packets/<task>/000001.json
<state_dir>/execution/receipts/<task>/000001.json
                                      000002.json
<state_dir>/resource_usage/<task>/000001.json
```

The state directory is always supplied by the caller; `.gitignore` carries
`state/` so runtime state is never committed by default. No database, no index
file: a directory listing sorted by sequence answers "every attempt at task X"
and cannot disagree with the files.

## CLI

```
python -m company.runtime packet <task.json> --branch B [--allow P] [--forbid P] [--test T] [--state-dir D]
python -m company.runtime receipt <receipt.json> --task <task.json> --state-dir D
python -m company.runtime execution --state-dir D --task <id>
```

`receipt` exits 1 on a rejected attempt, so a shell caller can branch on it.

## Tests

`tests/test_company_session_execution.py` — 44 focused tests covering
deterministic and reference-only packet generation, fingerprint stability,
preserved context fingerprints, the no-subagent rule at every link, branch
preservation, allowed/forbidden paths, malformed SHAs, remote mismatch,
attempted authority escalation, separate retained attempts, the canonical usage
record and the compact handoff that references it, no silent overwrite, the
provider hint changing nothing, and production independence — and, since the
fail-closed correction, the canonical default contract granting no write
authority, an explicit narrow grant bounding a packet exactly, `may_not_modify`
outranking `may_write`, and a write-producing accepted result having to prove a
clean working tree.

Combined Company OS suites: 301 passed.

## Invariants preserved

- Production systems import nothing from `company/`, `ai_platform/` or
  `knowledge/` (asserted by test, not just by review).
- No new dependency; standard library only.
- No subprocess, no vendor SDK, no async, no scheduler in the execution layer
  (asserted by test).
- Existing Company OS behaviour and file layouts unchanged.

## Unresolved risks

1. **A read-only result may still omit `working_tree_clean`.** For an accepted
   result that could have written — the packet granted a writable path, or the
   receipt names a changed file — an unreported tree is now a failure, because
   the protocol ends in a clean tree and silence is not evidence of one. The
   remaining gap is the genuinely read-only result that changed nothing: there
   `None` is recorded as a warning, since there was nothing that could have
   been left dirty. A tool that writes but reports neither its files nor its
   tree would slip through, and only the scope guard would catch it.
2. **Substance verification is opt-in.** Without `repo_dir`, `remote_verified`
   is a claim the runtime believes, as is the reported `remote_branch_sha` it
   is checked against. That is inherent to a transport boundary — the
   alternative is a network call from the control plane, and the boundary must
   keep working when the worker checkout is not reachable from here. The
   stronger local check stays available and stays optional.
3. **`invariants_preserved` lands in usage `notes`.** The canonical copy is the
   receipt file, which the handoff references; the note is a convenience and
   could drift if someone edits one and not the other.

## Recommended next step

Integrate Phases 1–4 on a single branch and run one real task end to end: a
packet prepared here, executed by a genuinely independent top-level session,
and its receipt ingested — measuring resources per accepted deliverable from
the ledger rather than from estimates.
