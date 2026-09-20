# Project Factory: the pre-media-loop baseline

The state of this repository at the point where the Simulation Factory
production system and Company OS stopped being two parallel lines of work and
became one branch, immediately before Autonomous Media/Growth Department
development begins.

---

## 1. The baseline

| | |
|---|---|
| main | `97b6894fbd0118c107f21ccffc3bd11bf8c4bd5c` (the consolidation merge) |
| milestone tag | `project-factory-pre-media-loop-v1` → `97b6894` |
| Company OS tag | `company-os-bounded-engineering-v1` → `1ecd396` |
| main before | `8b1022aec899c7fa72ca77f2a1441c4d1b4ff48f` |
| Company OS before | `company-os-v1-bootstrap` @ `1ecd396` |
| integration | fast-forward of `main` onto one merge commit |
| full suite | 5701 passed, 440 skipped, 18 failed — the same 18 as `8b1022a` |
| integration gate | READY, 34/34 required checks, 0 blockers |

This document was written after the tag, so `main` carries one documentation
commit on top of `project-factory-pre-media-loop-v1`. The tag marks the
consolidation itself.

## 2. Why this was a merge and not a rebuild

`main` and `company-os-v1-bootstrap` diverged at `eaca65e` (`v26-integration`)
and **never touched the same file again**. From that base:

| | files changed | added | modified | deleted |
|---|---|---|---|---|
| base → main | 263 | 259 | 4 | 0 |
| base → bootstrap | 623 | 622 | 1 | 0 |
| overlap | **0** | | | |

`main` carried the production line forward through V27–V33.1 in `race2/`,
`sloped/`, `godot/`, `audio/` and `tools/`. The bootstrap branch carried
Company OS in `company/`, `ai_platform/`, `intelligence/`, `knowledge/` and
`tools/engineering_runner/`. The merge is therefore additive in both
directions: the merged index is the exact union of the two trees, 2161 files,
with nothing missing from either side and nothing present in neither.

The one file both sides could have fought over is `pytest.ini`, and they did
not: `main` added a `slow` marker to the bootstrap branch's version, so main's
is a strict superset. `.gitignore` gained 17 lines from the bootstrap side —
`state/`, `.env*`, `.secrets/`, `client_secret*.json` and the YouTube token
files — and lost none.

Because the merge commit's first parent is `8b1022a`, `main` reached it by a
genuine fast-forward. No history was rewritten, nothing was squashed, and both
parent histories remain walkable.

## 3. What Company OS brings to main

Verified present at `1ecd396` before integration, and exercised by the suites
after it:

- Company OS foundation and governance (`company/delegation_policy.yaml`,
  `company/permissions.yaml`, the shadow probes)
- resource efficiency, and the repository/read-efficiency work (V1, V2, V3A)
- engineering orchestration (`company/engineering/orchestrator.py`) and the
  external engineering runner (`tools/engineering_runner/`)
- authority and reporting; receipt pre-validation (`validate_receipt`)
- developer attempt accounting; organization and workforce
- the Engineering Manager, the CFO, and an independent software reviewer
  (`code_review` as its own capability, distinct from `software_architecture`)
- objective planning, the candidate register, executive planning, bounded
  discovery, execution-viability preflight
- management by exception, the objective lifecycle, and CEO reporting
- bounded routine engineering as an operating mode
- internal integration protection; the production integration gate
- the runner's `--no-push` preflight, and `authorized_branch` / `base_commit`
  on `WorkOrderProposal`
- the validated intake fixes already promoted into canonical

## 4. Bounded engineering semantics

**Default is shadow, and there is no global switch.**

Three layers, each strictly more restrictive than the one above:

```
delegation_policy.yaml   who could ever approve this
ObjectiveContract        what this one objective authorized
evaluate_live            whether this specific request may proceed
```

- `company/delegation_policy.yaml` declares `mode: shadow` and always will:
  `company/delegation/shadow.py` probe 5 refuses at construction any policy
  declaring anything else.
- The operating mode lives in a per-objective CEO `ObjectiveContract`, never in
  a configuration file. `python -m company.delegation objective-contract`
  answers `shadow` unless `--enable-bounded-engineering` is passed explicitly.
- Live authority additionally requires a `PilotActivation` passed by hand.
  `evaluate_live()` with no activation authorizes nothing.
- There are exactly two operating modes, and adding a third is a source change,
  not a configuration value.
- A terminal or revoked objective, or an expired contract, leaves no residual
  authority.
- `BOUNDED_ENGINEERING_DEPARTMENTS` is `{"engineering"}` and
  `BOUNDED_ENGINEERING_MAX_RISK` is `MEDIUM`.

Verified from `main` itself:

```
SHADOW MODE: ENFORCED
  [ok] ceo_decision_names_a_human
  [ok] approval_carries_no_merge_authority
  [ok] only_ready_for_approval_can_be_approved
  [ok] delegation_record_cannot_act
  [ok] policy_cannot_leave_shadow

PROTECTED REFS (never advanced by any delegated decision)
  company-os-v1-bootstrap
  main
  master
```

Deployment policy, from `main`: `activated: false`, and every kind is *granted
to no seat*. `public_deployment` and `content_publishing` are `ceo_reserved`
and irreversible. `canonical_merge` is `executive_approval` — promotion to
canonical or `main` is not routine engineering authority.

135 tests in `tests/test_company_bounded_engineering_activation.py` and
`tests/test_company_bounded_engineering_autonomy.py`, and 750 more across
delegation, planning, review separation and engineering execution, assert these
properties. All pass at this commit.

## 5. Simulation Factory production state

Intact and unchanged by the merge. Race #2 V33.1 is shipped and frozen
(`race2-v33.1-test4-uploaded`); Race #2 V32.2 is shipped
(`race2-v32.2-uploaded`).

Green at this commit: the simulation engine (`tests/test_simulation.py`),
race and course generation, the race and race2 pipelines, the sloped race,
the marble3d simulation and its determinism check, evaluation (battle,
balance, scoring, candidate curation), encode, production delivery and QC,
the renderer, the V33.1 runout fix and the V32.2 ASMR audio pass.

## 6. Known failures, by identity

18 tests fail at `97b6894`. The same 18 node ids fail at `8b1022a` with the
same causes, so the merge introduced none of them.

| count | cause |
|---|---|
| 12 | branch-diff guard tests (`test_the_branch_changes_only_…`, `test_no_locked_file_moved[…]`) that compare the checkout against a feature-branch base and cannot pass from `main` |
| 5 | `tests/test_sloped_v251_world.py` and `tests/test_sloped_v252_world.py` — gitignored render artefacts under `output/sloped_race_v1/` are absent |
| 1 | `tests/test_neon_proof.py::test_a_missing_godot_is_reported_rather_than_raised` — Godot is not on `PATH` |

None was regenerated: the assets are not required by the baseline.

## 7. Known technical debt, carried not fixed

Recorded here deliberately. None of it blocks the baseline.

1. **`pilot*.py` naming.** Seven modules in `company/delegation/` are still
   named for the pilot phase that produced them: `pilot.py`,
   `pilot_correction.py`, `pilot_envelope.py`, `pilot_integration.py`,
   `pilot_record.py`, `pilot_report.py`, `pilot_simulation.py`. They are the
   live authority runtime, not pilot scaffolding.
2. **Semantic capsule ownership.** The integration gate's one advisory failure:
   `architecture.subsystem_ownership_bounded` reports 7 modules that no capsule
   claims, including `company/workforce/*` and `knowledge/__init__.py`.
   `tools/` is owned by nobody at all. Advisory, not required.
3. **Reserved/credential negation.** `screen_reserved` and `screen_credentials`
   in `company/engineering/intake.py` match trigger terms by plain substring,
   so a negated objective ("do *not* deploy publicly") still escalates. It
   fails closed — toward the CEO — so it is noise, not a hole.
4. **Provider usage event id.** No field on `ResourceUsageRecord` is a stable
   per-event identifier; `task_id` is the closest and is not unique per event.
5. **Mixed currency.** `Money` refuses arithmetic across currencies and holds
   no conversion. Correct today, a limitation the moment a second currency is
   really used.
6. **Deployment policy gaps.** Classified but granted to no seat. Fine for the
   current operation; the grant is a separate CEO decision.
7. **Runner telemetry.** Cost is session-total while turns and tokens are
   final-segment.

## 8. Production-worthy work deliberately left outside main

Four engineering jobs reached `ready_for_approval` with a reviewer PASS and a
READY gate, and were never approved or merged. Their code is absent from
`main`. They are held, not dropped, because `APPROVE` is CEO-reserved and a
consolidation may not issue it.

| branch | commit | what it adds |
|---|---|---|
| `eng-attempt-ledger` | `d681c5a` | `company/engineering/attempt_ledger.py` — every developer attempt on a job and what each cost |
| `eng-scope-usage` | `be5255d` | which authorized paths a work order actually touched |
| `eng-stage-timing` | `ae703ff` | `StageTiming` / `EngineeringJob.stage_timings()` from recorded transitions |
| `eng-governance-drift-check` | `d59a5d9` | `company/engineering/verify.py` and a read-only `verify` CLI |

Each needs a CEO decision before it can enter `main`.

`eng-ai-resource-efficiency-v2` (`5c1c035`) is **not** in this list: it was
REQUEST CHANGES, and only its operational subset (`company/efficiency/
strategy.py`) was promoted, via `eng-ai-resource-efficiency-v2-operational`,
which is in `main`.

## 9. What was preserved, and what was deleted

**Preserved.**

- Every commit on every branch that was merged: all of it is reachable from
  `main` and always will be.
- `company-os-v1-bootstrap` @ `1ecd396`, kept as a branch *and* tagged
  `company-os-bounded-engineering-v1`.
- All six tags, each verified reachable from `main`.
- Four local-only branches' unique commits, pushed to `origin` before any
  cleanup: `marble-visual-polish` (2 commits), `v271-contained-hall-finish`
  (1), `v272-contained-hall-merge` (3). They had existed on no remote.
- The four CEO-decision branches in section 8, local and remote.
- Every branch not contained in `main`: the V21–V24 and V27 labs, the pilot
  and dogfood execution records, the burn-in and classifier branches, the
  `eng-*` probe branches and the `benchmark-c*` / ctags / tree-sitter research.
- `wt-v27-contained`, the one worktree holding 262 MB of un-gitted `exports/`
  and 478 MB of render output that exists nowhere else.
- The ten `.benchmark-c2/runs/*` worktrees, which git refused to remove without
  `--force`. `--force` was not used.

**Deleted.** 70 local and 73 remote branches, every one proven by ancestry to
be fully contained in `main`. 32 worktrees, each verified clean, on no
in-progress operation, and holding no unique file. Approximately 16.3 GB of
working-tree copies recovered.

## 10. Repository shape now

| | before | after |
|---|---|---|
| local branches | 134 | 64 |
| remote branches | 143 | 72 |
| worktrees | 44 | 12 |
| tags | 4 | 6 |
| stashes | 0 | 0 |

`git status` is clean. No stale lock files, no tracked build output, no
credentials — `tools/youtube_fetch/secrets_.py` is a redaction module, and the
only credential-shaped literal in the tree is a fake token inside a test that
asserts redaction works.

The primary working tree remains checked out on `v21-visual-contrast`, where
this consolidation found it. `main` is not checked out anywhere.

## 11. Final closure: the four approved engineering items

**Superseded sections.** Sections 1, 8, 9 and 10 describe the state at
`97b6894`/`1224085`. This section records what happened after, and where the
two disagree, this section is current.

On 2026-09-21 the CEO approved the four `ready_for_approval` items held back in
section 8, and they were integrated onto `1224085` by curated cherry-pick.

| | |
|---|---|
| final main | `539daa71d9888278b219bf896cf9f94a249a3640` |
| final milestone tag | `project-factory-pre-media-loop-final-v1` |
| earlier tag, unmoved | `project-factory-pre-media-loop-v1` → `97b6894` |
| full suite | 18 failed, 5725 passed, 440 skipped |
| integration gate | READY, 34/34 required, 0 blockers |

Each was verified independently before integration: branch tip still equal to
the approved SHA, reviewer PASS, gate READY with 0 blockers, exactly one commit
beyond its merge-base with main, still absent from main, and no governance
surface touched — no delta reaches `permissions.yaml`, `delegation_policy.yaml`,
`org_registry.yaml`, `operating_mode.py`, `pilot*.py` or `company/delegation/`
at all, and none adds network, subprocess or mutation capability.

| item | commit | added |
|---|---|---|
| `eng-attempt-ledger` | `d681c5a` | `company/engineering/attempt_ledger.py`, 286 ins |
| `eng-scope-usage` | `be5255d` | `ScopeUsage` + a SCOPE USAGE result section, 135 ins / 2 del |
| `eng-stage-timing` | `ae703ff` | `StageTiming` / `stage_timings()`, 137 ins / 1 del |
| `eng-governance-drift-check` | `d59a5d9` | `company/engineering/verify.py` + a read-only `verify` CLI, 422 ins / 5 del |

The cumulative delta is **980 insertions and 8 deletions over exactly 7 files** —
the precise arithmetic sum of the four reviewed deltas, across their exact
union. Nothing unrelated was carried in. 24 tests were added and all pass.

**Three integration differences, all disclosed.** Two were append-vs-append
collisions in `tests/test_company_engineering_execution.py` and
`company/engineering/__init__.py`, where main and an incoming delta add a new
section or import block at the same anchor; both sides were kept in each case
and nothing was edited. The third is substantive: the attempt-ledger's
multi-attempt test asks for `max_developer_attempts=2`, which was unconstrained
at its base. Main has since introduced resource profiles and refuses a request
naming more attempts than its profile allows — the default, `consumer`, allows
one. Main had already migrated its own multi-attempt tests by naming
`resource_profile="expanded"`; this test now does the same. The attempt count
under test is unchanged.

**A defect in the earlier cleanup, found and corrected.** Section 9 recorded 73
remote branches deleted as "fully contained in `main`". Three of them are also
used by the test suite as diff bases:

| ref | used by | tests |
|---|---|---|
| `origin/v29-switchyard-contained-integration` | `test_race2_v30_stage.py` | 2 |
| `origin/v30-contained-stage-v2` | `test_race2_v301_stage.py` | 3 |
| `origin/v31-race-readability-camera-track` | `test_race2_v311_track.py` | 11 |

Deleting them turned 16 tests into silent skips — 4 that were already failing,
and **12 that were genuinely passing**. Ancestry alone was the wrong test for
whether a branch is disposable; a ref can be dead as code and live as a
fixture. All three were restored on `origin` (each verified an ancestor of
`main`, so nothing new entered history), and the suite returned to its
documented fingerprint. Future branch cleanup must grep the test suite for
`origin/<name>` before deleting a ref.

## 12. Worktrees and storage, final

Twelve worktrees became three.

- **Ten `.benchmark-c2/runs/T*` removed.** Each held nothing but a byte-identical
  134-byte `.claude/settings.local.json` granting Bash permission to the local
  Python interpreter — disposable session metadata, identical across all ten,
  and no unique commits (their `f2116a5` is reachable from six `origin`
  branches). The stubs were deleted and each worktree removed normally; `--force`
  was never used. The real benchmark evidence in sibling `ground_truth/`,
  `infra_check/`, `mcp/` and `tsvenv/` was not touched. ~5.3 GB recovered.
- **`wt-v27-contained` preserved, deliberately.** Its 262 MB of un-gitted
  `exports/` is 37 files. Seven of them — `contact.png`, `finish.png`,
  `middle.png`, `opening.png`, `hook_card.png`, `envelope.txt`, `measures.txt` —
  are **byte-identical** to files already committed under
  `docs/validation/sloped_race_v1/v27_contained/` on
  `origin/v27-contained-environment-lab`. The genuinely unique content is the
  **20 mp4 comparison clips, 250 MB** (A/B/C variants plus a V26 control), which
  exist nowhere else. They are reproducible in principle — `sloped/v27_contained.py`
  and `tools/sloped_v27_contained.py` are committed and the seed is locked — but
  only with Godot, which is not on `PATH`, and a full re-render. V27 is a
  superseded direction (V30 is in `main`), so they are not regenerated and not
  deleted.
- **`wt-main` created** at `C:/Users/mgial/OneDrive/Documents/projects/wt-main`,
  clean, tracking `origin/main`, at the final SHA. This is the workspace for the
  next phase.
- The primary tree stays on `v21-visual-contrast`, untouched, in case another
  session holds it.

## 13. Next roadmap phase

**AUTONOMOUS MEDIA / GROWTH DEPARTMENT LOOP.**

Not started. Nothing in this consolidation authorizes it, and the four
properties it will have to work within are unchanged:

- shadow is the default, per objective
- bounded routine engineering needs an explicit CEO `ObjectiveContract`
- public deployment and publishing are CEO-reserved and granted to no seat
- promotion to canonical or `main` is not routine engineering authority
