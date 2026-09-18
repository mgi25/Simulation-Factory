# External Engineering Runner V1

*Company OS still cannot spawn a process. It no longer needs to.*

---

## 1. The decision this milestone was built around

The previous milestone ended with a boundary stated plainly:

> `production.no_publishing_capability` is a **required** integration-gate check,
> and `company/integration/boundary.py` implements it as: no Company OS module
> may import `subprocess`, `multiprocessing` or `pty`, or call `os.system`,
> `os.popen`, `os.fork`, `os.exec*`, `os.spawn*` or `os.posix_spawn`.

and a conclusion drawn from it: closing the automation gap would require
amending that policy, which is a CEO decision.

The CEO's answer was: **no amendment.** The policy is right. Build the actuator
somewhere else.

So this milestone adds no capability to Company OS. It adds a second process.
`production.no_publishing_capability` is byte-identical, still required, still
passing, and the control plane still holds no `subprocess` import anywhere.

---

## 2. Control plane and execution plane

```
  CEO                                                        the operator
   |                                                              |
   |  python -m company.engineering request                       |  once:
   v                                                              v
+------------------------------+          reads          +---------------------------+
|  COMPANY OS  (control plane) | <---------------------- |  tools/engineering_runner |
|                              |   python -m company...  |     (execution plane)     |
|  CEO objective               | ----------------------> |                           |
|  authorization               |   JSON on stdout        |  git worktree per job     |
|  work order = the ceiling    |                         |  launch a coding session  |
|  capability routing          |                         |  run git                  |
|  context selection           |                         |  run pytest               |
|  lifecycle state             |                         |  launch a review session  |
|  receipt validation          |                         |  run the gate's own CLI   |
|  review adjudication         |                         |  collect + sanitize       |
|  gate interpretation         |                         |                           |
|  the CEO result page         |                         |                           |
+------------------------------+                         +---------------------------+
   no subprocess. no socket.                                may spawn. may not decide.
```

The arrow that matters is the one that is missing. The runner **receives**
authority and never creates it:

| the runner reads | out of |
|---|---|
| which paths may be written | the work order's `authorized_paths` |
| which paths may never be touched | its `forbidden_paths` + the protected surface |
| which branch, which base commit | the work order, cross-checked against the packet |
| which tests must pass | its `required_tests` |
| how many attempts remain | its `max_developer_attempts` |
| what the acceptance criteria are | the capsule-derived criteria |
| what to do next | `JobState`, which Company OS moves and the runner does not |

and the one thing it produces - evidence - is validated by the side that issued
the authority.

### Responsibilities, stated once

**Company OS** decides: what is authorized, what the ceiling is, who implements,
who reviews, whether a receipt is believable, what a review adds up to, what the
gate report means, and what the CEO is shown.

**The runner** does: launch a session, make a worktree, run git, run pytest,
launch a second session, run the gate CLI, and hand back sanitized evidence.

**The backend** does: start one process with one prompt and return what it said.
Nothing more - `ClaudeCodeBackend` is about ninety lines and holds no business
rule.

**The CEO** does: submit an objective, and approve, request changes, or reject.
Merging remains manual and governed, as instructed.

---

## 3. Why the runner lives under `tools/`

`tools/` is a declared production root
(`company/integration/sources.py: DECLARED_PRODUCTION_ROOTS`). Two required gate
checks follow from that, and both are exactly what this package wants:

- `architecture.production_does_not_import_company_os` — the gate mechanically
  proves the runner cannot import the control plane. The boundary is not a
  convention; it is a check that fails.
- `production.no_publishing_capability` scans `scan.company_modules` only, so a
  production module *may* import `subprocess`. That is the whole reason the
  actuator can exist here and could not exist in `company/`.

This is the same split `tools/youtube_fetch` uses, and it was adopted for the
same reason rather than by analogy: the authenticated half of the YouTube path
cannot live inside a network-free control plane, and the process-spawning half
of the engineering path cannot live inside a spawn-free one. In both cases the
dependency is an artifact format, not an import.

**No architecture check was exempted, extended or amended to accommodate this
package.** One branch-scope guard was widened, visibly: the three research
suites keep a list of paths under production roots that may be *added* to
(`_ADDITIVE_PRODUCTION_PATHS`), which already held `tools/youtube_fetch/` and
now also holds `tools/engineering_runner/`. Those are branch-hygiene tests, not
gate checks, and the widening permits an addition and still refuses a
modification.

---

## 4. The protocol: no new record types

Section 4 of the brief asks for the smallest machine-readable protocol
necessary. The answer turned out to be **none**: every record the loop needs
already exists.

```
company.engineering brief        -> developer briefing JSON  -> AuthorityEnvelope
                                                             (parsed, never written)
      [ a real coding session, in a task worktree ]
git + pytest                     -> GitObservation + TestRun
                                 -> SessionReceipt            (the existing contract)
company.engineering receipt      <- validated, recorded

company.engineering review-brief -> reviewer briefing JSON   -> AuthorityEnvelope
      [ a second, separate coding session ]
                                 -> ReviewerAttestation       (the existing contract)
company.engineering review       <- adjudicated

pytest x11 + company.integration check -> the gate's own report
company.engineering gate         <- parsed, never computed

company.engineering result       -> the CEO page
```

`AuthorityEnvelope` is the only new type, and it is a *reading* of a briefing,
not a record: it is never persisted as authority, never sent anywhere, and
cannot contain anything the briefing did not.

### One field was added to Company OS

`python -m company.engineering receipt` now prints `receipt_fingerprint`.

It was the single identifier no command line could produce. A
`ReviewerAttestation` must name the receipt it answers by digest; the digest is
computed inside `ExecutionStore.append_receipt` and was printed nowhere, so
preparing a review meant opening a Python session to recompute it by hand. That
was the last per-job manual step with nothing to do with judgment. The change
prints a value the store already held; it grants nothing.

---

## 5. Enforcement that survives the prompt

The instructions a session receives say what it may change. That is a request.
These are the parts that do not depend on the session having read anything.

| moment | check | where |
|---|---|---|
| before | the briefing's packet scope **is** the work order's authorized paths | `AuthorityEnvelope.parse` |
| before | the packet's forbidden scope **is** forbidden + protected | `AuthorityEnvelope.parse` |
| before | packet task, branch and base agree with the work order | `AuthorityEnvelope.parse` |
| before | the persisted packet record's digest is the one the brief names | `AuthorityEnvelope.parse` |
| before | a reviewer packet grants no writable path | `AuthorityEnvelope.parse` |
| before | the worktree's git common dir **is** the configured repository's | `Workspace.assert_identity` |
| before | the base commit exists in this repository | `Workspace.ensure_worktree` |
| before | every protected governance file is digested | `digest_paths` |
| after | every changed path, read from `git diff --name-status` + porcelain | `verify_developer_changes` |
| after | no path outside `may_write`; no path inside `may_not_modify` | `PathRules.violations` |
| after | no protected digest moved | `protected_drift` |
| after | HEAD is on the authorized branch | `verify_developer_changes` |
| after | the base commit is still an ancestor of HEAD (no rewrite) | `verify_developer_changes` |
| after | no dependency file changed unless authorized | `verify_developer_changes` |
| after | the test evidence was recorded at the implementation commit | `assert_tests_describe` |
| after review | HEAD did not move and the tree is not dirty | `verify_reviewer_left_no_trace` |
| after review | the reviewer's session id differs from the developer's | `_review_stage` |

**The changed-path list never comes from the session.** It is `git diff
--name-status <base>..HEAD` over a worktree that started at exactly `<base>`,
unioned with `git status --porcelain`, with both sides of a rename counted. A
check fed the session's own account of itself would agree with it, and the case
this exists for is the session that under-reports.

**A violation is BLOCKED, not a retry.** The run stops with nothing committed
and nothing pushed. The truthful evidence still goes back - a `rejected` receipt
naming the violation, at no commit - because an attempt that exceeded its scope
is a fact the history has to hold; what does not happen is another attempt.
Widening is not a mistake a second try fixes.

### What is *not* enforced, stated plainly

The developer session runs with a tool allow-list and `acceptEdits`, in a
dedicated worktree. It is not sandboxed at the OS level: a session that ran
`cd` elsewhere and edited a file outside the worktree would not be stopped by
the runner *while it happened*. It would be caught afterwards only if the file
is inside the repository, because that is where the diff is read.

This is a real limit and the honest description of the containment is: the
runner enforces the boundary on the **result**, not on the **process**. Process-
level sandboxing (a container, or a filesystem jail) is the V2 item. The
mitigation today is that the job runs in a worktree nobody else uses, the
repository-visible result is fully checked, and the protected governance surface
is digested by bytes rather than inferred from a diff.

---

## 6. The handoff: leases, not a queue

There is deliberately **no pending list**. `JobState` already answers "what does
this work order need next", and a second list is a second answer that can
disagree with the first.

```
planning    -> brief, worktree, developer session, commit, tests, push -> receipt
developing  -> (a run died here) resume the same packet's session      -> receipt
testing     -> review-brief, a second session                          -> attestation
reviewing   -> (a run died here) resume                                -> attestation
gate        -> 11 suites, then `company.integration check`             -> the report
ready_for_approval / decision_required / blocked  -> nothing. The CEO's.
```

Execution-plane state - which process holds which job, and what happened - is
what Company OS must not hold, and it lives under a runner directory:

```
<runner_dir>/runs/<work-order>/lease.json             the current holder
<runner_dir>/runs/<work-order>/outcomes/000001.json   append-only history
<runner_dir>/runs/<work-order>/run-000001/...         transcripts, receipts, diffs
```

- **Claiming** creates `lease.json` with `O_EXCL`, so two processes racing for
  the same work order cannot both believe they won: the filesystem decides,
  not a check-then-write.
- **Held and fresh** → the second runner skips the job.
- **Held and stale** (heartbeat older than the lease window) → reclaimed, and
  the reclamation is recorded, because "a run that never ended" and "a run that
  ended badly" are different facts.
- **Released** → reclaimed silently.
- Staleness is a heartbeat comparison, not a liveness probe: a pid check is
  wrong across machines and wrong after pid reuse.
- **Restart-safe** because the lifecycle is the source of truth. A restarted
  runner reads the job's state rather than remembering what it was doing. A
  completed job is in a state the runner does not act on, so it is not redone.
- The outcome log is append-only (`O_EXCL`, `NNNNNN.json`), the same mechanism
  `company/runtime/state_paths.py` uses; the lease is a current position and is
  rewritten, because appending to it would mean reading a directory to answer
  "is anyone on this right now".
- **No secrets in tracked git.** The runner directory is outside the repository,
  and everything written into it passes through `redaction.Redactor` first.

---

## 7. The backend boundary

```
EngineeringRunner
    |
    v
CodingBackend                     protocol: name, available(), launch(request)
    |-- ClaudeCodeBackend         exercised: a real session, per stage
    '-- CodexBackend              implemented, probed, NOT exercised
```

`SessionRequest` in, `SessionOutcome` out. The backend adds nothing to the
instructions the runner built from the packet - no role-play preamble, no
quality exhortation, no retry-with-a-nudge. A backend that improved the brief
would be a second place where the work order is interpreted.

**Session separation** is enforced rather than assumed: each session gets a
pre-assigned UUID, `--no-session-persistence`, no resume flag, and its own
process; the runner compares the two ids and refuses to submit an attestation
produced by the developer's session. The reviewer additionally gets no writing
tool and no shell, and the worktree's HEAD and status are compared before and
after.

**`CodexBackend` is not claimed to work.** It was probed on this machine:
`codex exec` reaches the provider and is refused for every model the account
offers - the installed CLI (0.42.0) is older than the only available model
(`gpt-5.6-sol`), and the three older model names are refused for a ChatGPT
account. `available()` therefore probes with a real one-line request rather than
trusting `--version`, which answers perfectly on a CLI that cannot complete a
single call. The adapter is kept because writing the second one is what
discovers the assumptions the first one baked in, and because Codex enforces
read-only at the sandbox rather than through a tool list - a stronger guarantee
than the Claude backend can give.

---

## 8. What the runner cannot do

| | why not |
|---|---|
| widen a work order | the envelope is parsed from the brief; nothing here writes one |
| approve | `ControlPlane` has no `decide`; the CLI has no `approve` |
| merge | `Workspace` has no merge, rebase, tag or force-push - asserted by a test that reads the string constants, because the docstrings discuss merging at length |
| deploy or publish | one outward call, `push`, of one branch to one remote, which the completion protocol requires |
| review its own work | Company OS routes the two roles to disjoint capabilities, and the runner refuses matching session ids |
| certify itself | it computes no readiness and no review outcome; both are read from replies it did not produce |
| run a shell | every call is an argv list; `shell=True` appears nowhere, asserted by reading the keyword off the call rather than the word off the page |
| read a credential | no module but `redaction.py` touches the environment, and that one reads names in order to remove values |

---

## 9. The tests

`tests/test_external_engineering_runner.py` — the runner, driven without a model
and without Company OS. A scripted control plane, a scripted backend, and **real
git**: a temporary repository with a real bare remote, because git is what the
authority check reads and a fake git would only prove the fake agrees with
itself.

`tests/test_company_external_engineering_runner.py` — the only module in the
repository that imports both halves. The runner restates four things the control
plane owns, and a restatement can drift, so each is pinned:

| the runner's copy | pinned against |
|---|---|
| `PathRules` | `company.runtime.path_scope.PathScope` |
| `normalise_path` | its counterpart, on the same refusals |
| the job-state names, `ACTIONABLE` | `company.engineering.lifecycle.JobState` |
| `REQUIRED_SUITES` | `company.integration.suites.REQUIRED_SUITES` |
| `build_receipt` | `SessionReceipt.from_mapping` + `validate_receipt` |
| `build_attestation` | `ReviewerAttestation.from_mapping` |
| `executor_hint` | `company.runtime.packets.ExecutorHint` |

plus the regression this milestone must not cause: the policy is still required,
and `PROCESS_MODULES` is asserted **by value**, because an exemption would most
plausibly arrive as a quiet edit to a frozenset rather than as a change to the
policy.

---

## 10. What the CEO does now

Two commands exist in the whole experience, and one of them is run once ever by
the operator.

**The operator, once:**

```
python -m tools.engineering_runner watch \
  --repo-root . \
  --state-dir  state/external-runner \
  --runner-dir ../company-os-runner-state \
  --worktree-root ../<repo>-runner-worktrees
```

It prints one JSON line per event and then sits idle, polling.

**The CEO, per piece of work:**

```
python -m company.engineering request --request-file objective.json \
  --state-dir state/external-runner --repo-root .
```

where `objective.json` is the existing `CEORequest` contract - an objective in
a sentence, a branch to work on, a base commit, and how many attempts are
authorized. The CEO names no file and no module: intake derives the scope from
the capsule that owns the subject, or stops with DECISION REQUIRED and the
capsule list.

**Then the CEO watches**, with the commands that already existed:

```
python -m company.engineering status --work-order WO --state-dir S
python -m company.engineering result --work-order WO --state-dir S
python -m company.dashboard ...
```

and sees the lifecycle move on its own:

```
REQUESTED -> PLANNING -> DEVELOPING -> TESTING -> REVIEWING -> GATE -> READY_FOR_APPROVAL
```

or stop at `DECISION_REQUIRED`, `BLOCKED` or `FAILED`.

**The CEO decides**, with the command that already existed:

```
python -m company.engineering decide --work-order WO --decision-file d.json --state-dir S
```

`APPROVE` records an approval and merges nothing. Merging stays manual and
governed until it is separately authorized, exactly as instructed.

---

## 11. Every manual step that remains

**One-time, per operator:**

1. Start the runner (`watch`). It survives individual job failures and keeps
   going; it is stopped with Ctrl-C.
2. Have `claude` (or another implemented backend) installed and authenticated.
   `doctor` answers whether it is, without spending a session on the question.

**Per engineering job:**

1. **Write the CEO request** - the objective, the branch, the base commit. This
   is the work being requested; it is not automation overhead.
2. **Read the result and decide.** Deliberately manual. `APPROVE` is the CEO's
   and nothing else may produce it.
3. **Merge, if the CEO approves.** Deliberately manual, and the runner holds no
   code that could do it.

**No longer per job:** launching a developer session, launching a reviewer
session, running pytest, running git, verifying the remote SHA, running the
integration gate, assembling suite evidence, writing a receipt, computing the
receipt fingerprint an attestation needs, writing an attestation.

---

## 12. Cost, and the one thing worth watching

Each job spends two model sessions plus the eleven required suites. The receipt
carries the developer session's real token counts and provider cost, taken from
the backend's own reply rather than estimated, so the usage ledger and the
finance layer see an automated run the same way they see a manual one. The
`attempt_ledger` view the dogfood added exists precisely so a CEO can see
whether an automated run is converging or thrashing before it has spent the
work order's whole attempt budget.

---

## 13. The dogfood: two real CEO requests

The operator started the runner once and typed nothing else at it. Everything
below - every session, every commit, every pytest run, every gate evaluation,
every receipt - was performed by the runner.

### Job 1 — `wo-attempt-ledger`

| | |
|---|---|
| CEO objective | "Show me, for one engineering job, every developer attempt that was made and what each one cost, so I can tell whether an automated run is converging or thrashing without reading the whole history." |
| derived scope | `company/engineering`, `tests/test_company_engineering_execution.py` — the CEO named no file |
| work order | `wo-attempt-ledger`, fingerprint `4418d6288e06d39d`, 8 acceptance criteria |
| forbidden | 6 paths including `tools` — so the work could not touch the runner |
| packet | `1f146021562d64ef`, attempt 1, authority `5dc2144936813db2` |
| developer session | `10faa7dd-a262-4595-95b9-b154325437d6`, claude-opus-4-6[1m], 48 turns, 287 s, $2.14 |
| implementation | `company/engineering/attempt_ledger.py` + its export + 4 tests — 3 files, 286 insertions |
| authority check | 7 checks, 0 violations; 10 protected digests unchanged |
| commit | `d681c5a1b970470bd98c54f352f4f969f97f5ab2` on `eng-attempt-ledger`, pushed, remote SHA verified against the real refs |
| required tests | `tests/test_company_engineering_execution.py` — 100 passed (95 before, 5 new) |
| receipt | accepted, 0 validation failures, fingerprint `08cd3fd92f1e7f99` |
| reviewer session | `5b33b7ea-49ff-497b-bd53-6a76d37ea003`, a different process and a different id; worktree HEAD and status identical before and after |
| review | PASS by `chief_architect`; attested PASS, deterministic PASS; 8/8 criteria answered; 2 advisory findings |
| gate suites | the 11 required suites, 780 tests, all green, run at `d681c5a` |
| gate | READY, `integration-readiness-2026-09-18-a1e954d2bc971f33`, 0 blockers, not stale against `d681c5a` |
| final state | **ready_for_approval**, and not merged |

Both review findings were real: one flagged that the usage-to-attempt
correlation relies on records arriving in sequence order (which the implementer
had disclosed as a risk), and one caught three imports the new module never
uses.

### Job 2 — `wo-scope-usage`, start to finish in one run

The second request was submitted while the runner was already up, and it moved
from `planning` to `ready_for_approval` inside **one** run, with nothing typed
at the runner in between.

| | |
|---|---|
| CEO objective | "For one work order, show me which of the paths it was authorized to change the work actually touched, so I can see how much of the scope I granted was used." |
| work order | `wo-scope-usage`, fingerprint `8d57bdf95a8685de`, 8 acceptance criteria |
| developer session | `d964d8c3-1775-4881-b529-6cd3a3ae5b1f`, 38 turns, 219 s, $1.41 |
| implementation | `company/engineering/result.py` + its export + tests — 3 files |
| authority check | 7 checks, 0 violations |
| commit | `be5255dfbacc…` on `eng-scope-usage`, pushed, remote verified |
| required tests | 101 passed |
| receipt | accepted, 0 validation failures, fingerprint `34501f387bb08279` |
| reviewer session | `fbf4cf22-71c7-4890-aeff-2b5914f2f3f9`, 7 turns, 62 s, $0.31 |
| review | PASS by `chief_architect`; 1 advisory finding |
| gate | READY at `be5255d`, 11/11 suites green, 0 blockers |
| final state | **ready_for_approval** |

Three stages, two sessions, one run, and the only thing a person did between
starting the runner and reading the result was type the request.

---

## 14. What the dogfood found

The loop ran; the runner had five defects, and every one of them was a case a
unit test could have caught and did not, because each was an assumption about
the *other* side of the boundary.

| what broke | why | now |
|---|---|---|
| every review packet was refused | the envelope compared the review packet's task id with the work order id; `review_specification` builds `<work_order_id>-review`, because the two roles route to different employees and that difference *is* the separation of duties | both directions asserted; the suffix pinned to the control plane's own id |
| the protected surface was re-read in the wrong tree | `--repo-root` for `review` was the operator's checkout, not the task worktree, so the one check that can catch an unmentioned edit read files no session could have touched | the task worktree, asserted |
| a resumed review could not find its attempt | the review looked for the developer stage inside its own run directory, and a runner restarted between the two resumes in a new one | searches earlier runs, asserted |
| a 424-character `evidence_ref` cost a whole review session | the brief never said what a reference is, and Company OS refused the attestation one stage later | the brief says one line and 200 characters, and the same budgets are applied when the session answers, so the bounded repair loop restates it |
| the gate's cross-check silently did not run | the runner looked for a `readiness` field the report does not have and passed an empty `--reported-readiness` | read from the gate CLI's exit code, which is where its verdict lives |

A sixth was found by reading rather than by running: a session that changes
nothing committed nothing, produced an empty diff, and passed the required
tests *because they passed before it started* — so an empty attempt read as a
success. It is a rejected attempt now.

The first three were found by job 1, which therefore took three runner starts.
Job 2 ran clean in one. Job 3 was run on the frozen code, after every fix, to
establish that the code being shipped is the code that completed a request.

---

## 15. Security properties, and where each is asserted

| property | asserted by |
|---|---|
| the runner cannot expand `may_write` | `test_the_runner_cannot_expand_may_write_by_editing_the_packet` |
| dropping the packet's forbidden list is refused | `test_dropping_the_packets_forbidden_list_is_also_refused` |
| an unauthorized changed path → BLOCKED | `test_a_change_outside_may_write_blocks_the_run_and_commits_nothing` |
| protected-policy drift → BLOCKED | `test_a_protected_policy_that_drifted_is_a_violation_even_with_a_clean_diff` |
| a wrong base commit → refused before the work | `Workspace.ensure_worktree`, `test_a_packet_expecting_another_base_commit_is_refused` |
| a rewritten history → BLOCKED | `test_a_rewritten_history_is_a_violation` |
| a wrong worktree or repository → BLOCKED | `Workspace.assert_identity`, `test_the_wrong_worktree_is_a_violation` |
| a packet/work-order fingerprint mismatch → BLOCKED | `test_a_packet_fingerprint_that_disagrees_with_the_stored_record_is_refused` |
| a test result for the wrong SHA → refused | `test_a_receipt_cannot_be_built_from_evidence_for_another_commit` |
| the reviewer session is a different session | `test_the_developer_and_reviewer_run_in_different_sessions` |
| self-review is refused | `test_a_review_that_routes_back_to_the_implementer_is_refused` |
| gate evidence for the wrong SHA is refused | `_gate_stage` refuses a worktree not at the implementation commit; Company OS refuses a stale report |
| the runner cannot issue a CEO approval | `test_the_runner_cannot_issue_a_ceo_decision` |
| the runner cannot merge | `test_the_runner_holds_no_merge_deploy_or_publish_capability` |
| duplicate execution is prevented | `test_a_second_runner_cannot_claim_a_job_already_in_flight` |
| a restart does not repeat completed work | `test_a_restart_does_not_repeat_completed_work` |
| a failed job is recorded and the lease released | `test_a_failing_stage_is_recorded_and_does_not_leave_the_lease_held` |
| secrets are redacted from persisted logs | four tests with recognisable sentinels |
| Company OS still holds no process-spawn capability | `test_company_os_still_holds_no_process_spawning_capability`, and the gate check itself |
