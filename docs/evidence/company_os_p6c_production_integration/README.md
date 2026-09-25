# P6C — production integration record

P6C (the experience store), with its one independently reviewed correction
P6C-R1, integrated into `main` on 2026-09-25. This directory is append-only.
It does not rewrite `docs/evidence/company_os_p6c_experience_store/` (the P6C
record) or its `p6c-r1-failsafe-correction/` subdirectory, which stay exactly
as the approved branches archived them.

## The SHAs

| | |
|---|---|
| starting `main` (first parent of the merge, and the merge base) | `4fd5fafa92767a83afb966c9a2210fdb016fc28d` |
| P6C implementation (frozen) | `16d5a39cc9d1230f82301850b9195322300b7fd1` |
| original P6C evidence (`p6c-experience-store-v1`) | `e4eb260278be5f5bec2d925ad05315afb0969634` |
| P6C-R1 correction (the behaviour change) | `0d697d87e87e1eb4e98585c1f9a4e1a9c4a90238` |
| P6C-R1 evidence, the integration candidate (`p6c-experience-failsafe-fix-v1`) | `c22a1bed633207b93106c07f6da2f9cd3bcb5a61` |
| integration merge (`--no-ff`, branch `integrate-p6c-v1`, local only) | `c931091e884c5dedc62379fb616f6d09ef234f5e` |
| merge tree | `2b8215ddfad28c2c9f0d03d65ea4cc4f51d14b84` (= the tree of `c22a1be`) |
| `main` after the push | `c931091` (this archive commit lands on top of it) |

## Review lineage

1. The independent P6C review returned **CHANGES_REQUIRED** with exactly one
   blocker, **B1**: a malformed experience advisory could kill the external
   engineering runner instead of degrading to no advice (a mapping-valued
   `why` raised KeyError, deep nesting raised RecursionError, an unforeseen
   RuntimeError escaped, and an OSError on the advisory write ended the run
   `failed`).
2. The correction `0d697d8` adds strict `why`/`lines` shape validation
   (`_strings` in `tools/engineering_runner/experience.py`) and wraps the
   optional experience path (advisory write, parse, revalidate, record write)
   in `except Exception` in `EngineeringRunner._experience`, leaving
   `BaseException` uncaught.
3. A fresh independent P6C-R1 re-review returned **PASS**: B1 closed, authority
   unchanged, required set 47 / `f5de72a66d79bb83`, no correction-introduced
   regression. It recorded one nonblocking finding: the suite's depth-based
   recursion test could fail while *building* its payload on Windows /
   Python 3.13, before the runner is invoked. See
   [The recursion-depth fixture](#the-recursion-depth-fixture).

## Topology and overlap

Recomputed after a fresh fetch, not copied from the brief. `origin/main`,
`origin/p6c-experience-store-v1` and `origin/p6c-experience-failsafe-fix-v1`
were exactly the expected SHAs, on the local remote-tracking refs and on
`git ls-remote`.

| | |
|---|---|
| ancestry | `4fd5faf` → `16d5a39` → `e4eb260` → `0d697d8` → `c22a1be`, each an ancestor of the next |
| `e4eb260..0d697d8` | exactly 1 commit, 4 files: `tools/engineering_runner/{experience,runner}.py` and their two test files (334+, 17−) |
| `0d697d8..c22a1be` | exactly 1 commit, 9 files, all added under `docs/evidence/company_os_p6c_experience_store/p6c-r1-failsafe-correction/` (evidence only) |
| candidate vs `main` | 7 ahead, 0 behind, merge base `4fd5faf` |
| files changed on the candidate | 59 (48 added, 11 modified, 0 deleted, 0 renamed; 19999+, 5−) |
| commits on `main` since the base | 0 |
| overlap | **0** (nothing changed on `main` since the base) |

The 59 files: `company/experience/` 12 (new), `docs/evidence/` 32 (P6C + P6C-R1
records), `knowledge/company_os/capsules/seeds/` 2 (the new
`company-experience-store` capsule and `company-organizational-intelligence`'s
dependency list), `tests/` 6, `tools/engineering_runner/` 7.

`git merge-tree --write-tree origin/main origin/p6c-experience-failsafe-fix-v1`
returned tree `2b8215d` with no conflicts, equal to `c22a1be^{tree}`, so the
merge was known clean and exact before it ran. It produced exactly that tree.

## Structural integrity

* The merge has first parent `4fd5faf` and second parent `c22a1be`.
  `4fd5faf..c931091` is 8 commits: the 7 of the lineage plus the merge.
* `4fd5faf`, `16d5a39`, `e4eb260`, `0d697d8` and `c22a1be` are ancestors, and
  so are P6B (`d040dd9`, `50f4229`, `5da27cf`), P6A (`f2a5aa8`, `5e91cef`,
  `39fbd44`), P5 (`7861b6b`, `03e4336`, `6cf59c9`) and the Category 3 / video
  lineage (`2e7838a`, `d2a3002`, `bf0dd1f`). No history was rewritten.
* `git diff-tree c22a1be c931091` is empty. `diff(main → merge)` is identical,
  entry for entry, to `diff(base → c22a1be)`.
* 0 deletions. No path under `godot/`, `satisfying/`, `race2/`, `sloped/`,
  `audio/`, `tools/youtube_fetch/`, `company/integration/`,
  `company/engineering/`, `company/runtime/`, `ai_platform/`, `intelligence/`,
  `knowledge/company_os/records/` or the P5/P6A/P6B evidence directories is
  touched. The runner's authority files (`authorization.py`, `workspace.py`,
  `process.py`, `redaction.py`) are untouched.
* The merged tree contains `company/experience/` (12 files) and the P6C-R1
  runner: `_strings` validating `why`/`lines`
  (`tools/engineering_runner/experience.py`), and `_experience` wrapping the
  advisory write, `parse`, `revalidate` and the `experience.json` write in one
  `except Exception` (`tools/engineering_runner/runner.py`). There is no
  `except BaseException` and no bare `except:` anywhere in the runner package.

## Experience Store integrity

`experience-invariants-merged-tree.json` maps each invariant to the P6C tests
that pin it and their outcome in the merged-tree run. All 14 hold; every
mapped test was found and passed. Where this session also measured an
invariant directly, that is listed.

| # | invariant | tests | also measured here |
|---|---|---:|---|
| 1 | episodes index canonical records, not a second source of truth | 4 | |
| 2 | decision-time features separate from outcome fields | 5 | |
| 3 | observed / estimated / counterfactual provenance explicit | 5 | |
| 4 | identical capture is idempotent | 1 | re-capture on two real state-directory copies: 0 created, byte-identical store |
| 5 | a conflicting duplicate refuses overwrite | 3 | |
| 6 | stale history is not current precedent | 5 | replay: 5 `stale_only` abstentions; today 4 current / 19 stale |
| 7 | retrieval deterministic and explainable | 5 | replay fingerprint reproduced, repeat identical |
| 8 | weak / incompatible history abstains | 8 | replay: 10 `incompatible_only`, 8 `no_match` |
| 9 | corrections / failures are warnings, never success precedent | 5 | |
| 10 | KnowledgeStore not mutated automatically | 2 | [Knowledge separation](#knowledge-separation) |
| 11 | experience grants no authority | 43 | [Authority and safety boundaries](#authority-and-safety-boundaries) |
| 12 | missing / corrupt advice degrades to no advice | 31 | [B1 on the merged tree](#b1-on-the-merged-tree) |
| 13 | current P6B graph and current authority revalidate history | 6 | replay: 19/19 historical file suggestions refused by read authority |
| 14 | experience cannot reduce the required suites | 2 | [Required suites](#required-suites): 47 ⊇ main's 45; no scope narrows it |

## B1 on the merged tree

`probes/b1_probes.py`, written by this integration session and kept here, not
in `tests/`. Every case drives the real `run_one → _developer_stage →
_experience` path with the runner suite's own scripted control plane and
backend, and asserts the whole developer stage equals a run with experience
switched off (the suite's `_runs_as_without_advice`), plus, one by one: no
`## Prior experience` block, no file ranked for prior experience, an
unchanged execution-context file list, unchanged `may_read` / `may_not_read` /
`may_write` / `required_tests`, and the same developer model.

| probe | merged tree `c931091` | unfixed runner (control) |
|---|---|---|
| non-empty mapping as precedent `why` | no advice, job completes | `KeyError: slice(None, 4, None)` escapes `run_one` |
| warning `lines` = mapping / bare string / list with an int | no advice, refused by shape | mapping and int member **accepted** as advice; the string refused only by the line-count bound |
| RuntimeError from `parse` / from `revalidate` | no advice | escapes `run_one` |
| RecursionError forced at the `parse` seam | no advice | escapes |
| RecursionError forced at `_authority_keys`, inside the real `parse` | no advice | escapes |
| genuine recursion: `measurement` nested `getrecursionlimit() + 50` deep | no advice | escapes |
| `PermissionError` writing `experience-advice.json` / `experience.json` | no advice, job completes | the run ends `failed` |
| `KeyboardInterrupt`, `SystemExit`, `GeneratorExit` at parse / revalidate / advisory write (9) | propagate, no developer session launched | propagate |
| well-formed advice still reaches the brief (control) | used | used |

Merged tree: **21 passed** (`b1-probes-merged-tree.txt`). The unfixed control
is a throwaway detached worktree at `c22a1be` with only
`tools/engineering_runner/{experience,runner}.py` checked out from `e4eb260`:
**11 failed, 10 passed** (`b1-probes-unfixed-runner.txt`). All 11 B1 cases fail
there and pass on the merge; the 10 that pass on both are the process-control
cases and the well-formed control, which pin behaviour that never changed. So
the probes are sensitive to B1 and the merge closes it. The genuine-recursion
probe asserts first that the courier's `json.loads(json.dumps(payload))`
round-trips the payload and that the real `_authority_keys` raises on it, so
it is a payload the courier would deliver and the scan cannot walk.

On real pushed `main` the same probes, together with the authority probes,
gave **60 passed** (21 B1 + 39 authority; `b1-and-authority-probes-post-push-main.txt`).

## The recursion-depth fixture

The correction review's nonblocking finding: the suite's
`test_a_malformed_advisory_runs_the_job_exactly_as_without_advice[nested_past_the_recursion_limit-^RecursionError: ]`
builds a payload `getrecursionlimit() + 500` deep and can exhaust the
recursion budget while computing its fingerprint in test setup, before
`run_one` is called.

**It did not reproduce in this integration environment** (CPython 3.13.0,
MSC v.1941 64-bit, Windows 11, recursion limit 1000): it passed inside the
full 47-suite run (7.2 s), twice as its parametrised group alone (6/6), and
once as a single node (`recursion-fixture-classification.txt`). It is recorded
green, and the test was not edited. Independently of it, the functional B1
recursion invariant is proven three ways above (forced at the seam, forced at
the real recursion site, and a genuine just-past-the-limit payload). The
finding stays in the carried register: the depth margin is environment
dependent even though it held here.

## Required suites

`python -m company.integration required-suites --repo-root . --json` on the
merged tree (`required-suites-merged-tree.json`), resolved twice,
byte-identical:

| | |
|---|---|
| required suites | **47** |
| fingerprint | **`f5de72a66d79bb83`** |
| `unresolved` | `[]` |
| `undeclared_company_os_suites` | `[]` |
| origins | canonical 11, capsule_contract 35, dependency_observed 41 |
| dependency-observed only | 11 (P6B's formerly undeclared suites, intact) |

The payload equals P6C-R1's archived `required-suites.json` field for field.
Against `main`'s 45 (`72502df3cfb3cbb7`): nothing removed, exactly
`tests/test_company_experience_store.py` and
`tests/test_company_experience_retrieval.py` added (capsule_contract +
dependency_observed, capsule `company-experience-store`).

P6C cannot narrow the set: with `--changed-path` for
`company/experience/retrieval.py`, `tools/engineering_runner/runner.py`,
`tools/engineering_runner/experience.py` or `company/integration/suites.py`
the set stays 47 (2 to 6 suites gain `change_scope`, and the fingerprint
changes accordingly); `race2/race.py` leaves both at 47 /
`f5de72a66d79bb83`. The resolver never reads experience
(`test_the_gate_and_the_engineering_loop_never_read_experience`). Re-derived on
real pushed `main`: byte-identical (`required-suites-post-push-main.json`).

## Suite runs

Canonical `.venv`, CPython 3.13.0, where **PyYAML is not installed** (`import
yaml` fails). Nothing was installed. Runs were taken off OneDrive, from a
worktree in the local temp directory. JUnit XML per chunk; SuiteEvidence built
from it by `probes/build_suite_evidence.py`. Six suites are marked
production-environment (`company_os: false`), the same six P6B and P6C
marked: the four `tests/test_engineering_runner_*.py`,
`tests/test_external_engineering_runner.py` and `tests/test_youtube_fetch.py`.

| where | `origin/main` | evidence | result |
|---|---|---|---|
| the real integration branch `integrate-p6c-v1` @ `c931091` | `4fd5faf` | `suite-evidence-integration-branch.json` | 47/47 represented; **44 green**; 3261 passed / 3 failed / 1 skipped. The 3 failures are the research branch-scope guards, each listing the six **modified** `tools/engineering_runner/*` files (`branch-scope-guards-on-integration-branch.txt`) |
| a throwaway clone at `c931091` with GitHub-faithful refs and `origin/main` repointed to the merge (a model, used only to decide the push; no real ref touched, push URL disabled) | `c931091` (model) | `suite-evidence-merged-tree-premerge-model.json` | the three research suites 321/321; the other 44 carried from the branch run |
| **real pushed `main`** @ `c931091` | `c931091` (real) | `suite-evidence-post-push-main.json` | all 47 re-run on real `main`: **47/47 green, 3264 passed / 0 failed / 1 skipped**. The three research guards self-healed: `origin/main...HEAD` is empty and they pass 3/3 (`branch-scope-guards-post-push-main.txt`) |

## Focused validation

All from the merged-tree full run (`focused-validation-merged-tree.json`), all
green, 0 failed, 0 skipped:

| suite | passed |
|---|---:|
| `test_company_experience_store.py` | 57 |
| `test_company_experience_retrieval.py` | 77 |
| `test_company_external_engineering_runner.py` | 67 |
| `test_external_engineering_runner.py` | 203 |
| `test_engineering_runner_execution_context.py` | 80 |
| `test_company_dependency_graph.py` | 54 |
| `test_company_gate_suite_requirements.py` | 46 |
| `test_company_integration_gate.py` | 89 |
| `test_company_typed_evidence_context.py` | 59 |
| `test_company_efficiency.py` | 69 |
| `test_company_engineering_execution.py` | 207 |
| `test_company_execution_transport.py` | 14 |
| `test_company_read_authority.py` | 34 |
| `test_company_os_capsules.py` | 68 |
| `test_company_os_knowledge.py` | 26 |

The P6C-R1 regression tests are inside these: the 13 runner-level B1 tests in
`test_external_engineering_runner.py` and the 17 shape tests in
`test_engineering_runner_execution_context.py`, all passed.

No-subagent validation: 42 tests selected by name
(`subagent|nested_agent|nested_worker|nested_use|nested_session|sub_agent`),
42 passed. Protected-surface validation: 34 tests selected by name
(`protected`), 34 passed. The gate's `execution.no_subagent_runtime_lock`
passes.

## Replay

The historical corpus is on this machine and the replay is local and unpaid,
so it was re-run on the merged tree (`replay-reproduction-merged-tree.json`),
writing to a scratch directory. First,
`verify_evidence.py --projects` re-digested all 21 source directories against
the archived `replay-corpus.json`: 0 problems.

* Replay fingerprint **`3a115b210fdda3d6`**, repeat identical, equal to the
  archived one. `replay-corpus.json` and `replay-validity-today.json` are
  byte-identical to the archive. `replay-results.json` and
  `replay-summary.md` differ in 36 leaves, all `latency_ms`, which the
  fingerprint excludes by design.
* 24 captured attempts: 17 accepted, 7 corrections. 34 decisions, 11
  precedent matches, 23 abstentions (10 `incompatible_only`, 8 `no_match`,
  5 `stale_only`). 9/9 evaluable precedent rows had a top-1 precedent that
  changed a file the task changed. 19/19 historical file suggestions refused
  by read authority. Today: 4 current, 19 stale.

This is **newly remeasured** integration evidence, not carried. It is
mechanism evidence, not model accuracy, and no token or cost saving is
claimed.

## Full-suite regression

Merged tree, 168 test files in four chunks that cover each file exactly once
(`full-suite-per-file-merge.json`):

| chunk | failed | passed | skipped |
|---|---:|---:|---:|
| the 47 required suites | 3 | 3261 | 1 |
| other, part 0 (42 files) | 1 | 1454 | 3 |
| other, part 1 (41 files) | 12 | 1101 | 142 |
| other, part 2 (38 files) | 5 | 1315 | 295 |
| **total, 7593 tests** | **21** | **7131** | **441** |

0 errors, 0 collection errors (PyYAML absent). The triple equals the P6C-R1
measurement at `0d697d8` exactly.

**Classification by node id** (`full-suite-failures-merge.txt`). The 21 were
re-run as exact node ids on both parents, same machine, same session:

* at `4fd5faf` (pre-integration `main`): **18 failed, 3 passed**
  (`full-suite-failures-parent-main-4fd5faf.txt`). The 3 that pass are the
  research branch-scope guards.
* at `c22a1be` (the approved candidate): **21 failed**, identical ids
  (`full-suite-failures-parent-p6c-c22a1be.txt`).
* The 21 equal P6C-R1's archived `full-suite-failures-0d697d8.txt`, and the
  18 equal `main`'s recorded baseline (`baseline-failures-main.txt` in the
  P6C record): 12 stale race branch-scope guards, 5 sloped-world tests that
  need gitignored `output/` files, 1 neon/Godot test.

**Integration-introduced failures: 0.** The only failures not in `main`'s 18
are the 3 research guards, which fail by construction until `origin/main` is
the merge. On real pushed `main`, the same four chunks gave **18 failed /
7134 passed / 441 skipped** over the same 7593 tests, 0 errors, 0 collection
errors (`full-suite-failures-post-push-main.txt`,
`full-suite-per-file-post-push-main.json`): the same 18 node ids as
pre-integration `main`. The 3 research guards self-healed, so `main`'s
steady-state fingerprint stays **18 failed / 441 skipped**, now with 7134
passing tests.

No B1 crash returned and no PyYAML collection issue returned.

## Authority and safety boundaries

`probes/authority_probes.py`, merged tree: **39 passed**
(`authority-probes-merged-tree.txt`).

* Every item on the package's list, by the key a producer would have to use
  (`may_read`, `may_not_read`, `may_write`, `required_tests`,
  `reasoning_class`, `risk`, `employee` for specialist domain,
  `authorizes_merge`, `deploy`, `publish`, `readiness`, `resource_profile` for
  the model tier), is refused by `ExperienceAdvice.parse` at three depths
  (inside an unread top-level list, inside a suggestion, and deep inside
  `measurement`): 36 cases.
* The parsed `ExperienceAdvice` has exactly eight fields (work order id,
  fingerprint, status, abstention, precedents, warnings, files, tests); none
  can carry authority.
* A run with well-formed advice, and a run whose unread `measurement` carries
  words outside the vocabulary (`model_tier`, `specialist_domain`, `merge`),
  each keep the authority envelope, the developer model, tools, read-only
  flag, timeout, cost ceiling, adaptive-routing decision, final state and
  stage list identical to the no-advice run. Only navigation (the brief
  block, the primary-file ranking) differs.
* The suites pin the rest: `test_experience_cannot_move_the_adaptive_model_gate`,
  `test_a_risk_class_cannot_be_lowered_by_precedent`,
  `test_history_cannot_expand_the_read_scope`,
  `test_history_cannot_skip_or_replace_a_required_suite`,
  `test_the_runner_holds_no_merge_deploy_or_publish_capability`. The gate
  still passes `production.integration_remains_disabled`,
  `production.no_publishing_capability`,
  `execution.read_authority_fails_closed`,
  `execution.write_authority_fails_closed` and
  `execution.no_subagent_runtime_lock`.

**Import boundaries** (`import-boundaries-merged-tree.json`, AST and raw text,
with live positive controls: `company/experience → company.*` 15/15,
`tools/engineering_runner → json|subprocess` 12/12):

| boundary | AST | text |
|---|---:|---:|
| `company/experience` → `company.integration` | 0 | 0 |
| `company/experience` → `tools` / `tools.engineering_runner` | 0 | 0 |
| `tools/engineering_runner` → Company OS (`company`, `ai_platform`, `knowledge`, `intelligence`) | 0 | 0 |
| `company` → `tools.engineering_runner` | 0 | 0 |

The runner names `company.experience` only as the module string of a
subprocess (`ControlPlane.experience_advice` runs `python -m
company.experience suggest ... --json` and carries its stdout); every other
mention is a comment or docstring. The bounded artifact/CLI contract is the
only channel.

## Knowledge separation

`probes/knowledge_separation.py` (`knowledge-separation-merged-tree.json`):
snapshot copies of two real state directories (`repository-architecture-v1`,
the live one, and `company-os-repo-exploration-v2-state`) were exercised with
the real CLI: `capture`, a second `capture`, `list`, and `suggest` for all 13
work orders (9 precedent, 4 abstentions, all exit 0, all `advisory_only`).

* The whole `knowledge/` tree (53 files, 4 of them KnowledgeStore records) is
  byte-identical before and after.
* Every non-experience file in both state copies (177 and 32) is
  byte-identical; the original source directories are untouched.
* Only `experience/episodes/**` was written (8 + 1 episodes), in the episode
  schema. No Fact, Hypothesis, Decision, ExperimentLearning or
  FailureLearning record was created. The second capture created 0 and left
  the store byte-identical.

## Integration gate

`python -m company.integration check --repo-root . --suite-evidence <file>`,
no `--state-dir` (as in P6A and P6B). Policy v1: 35 required and 4 advisory
checks. `authorizes_production_integration` is `false` in every report: the
gate never authorizes; the CEO package did, conditionally.

| report | source | result |
|---|---|---|
| `gate-report-integration-branch.*` | `integrate-p6c-v1` @ `c931091`, `origin/main` = `4fd5faf` | **BLOCKED**, 34 pass / 1 fail required. The sole blocker is `health.required_suites_pass` over the three guard-bearing research suites, expected by construction |
| `gate-report-merged-tree-premerge-model.*` | `c931091`, `origin/main` modelled as the merge | **READY**, 35/35 required, 0 blockers. Used only to decide the push |
| `gate-report-post-push-main.*` | **real `main` @ `c931091`**, `origin/main` = `c931091`, fresh evidence from the post-push run | **READY**, 35/35 required pass, 0 fail, **0 blockers** |

The 2 advisory unknowns in each are `executive.decision_queue_preserves_source_refs`
and `workforce.capability_gaps_visible`, unknown only because no company state
directory was supplied; policy permits that. `health.production_failures_separated`
passes (the six production-environment suites, 0 failing).

## Push and preservation

`origin/main` was re-fetched immediately before the push and was still
`4fd5faf`, the merge's first parent, on the remote-tracking ref and on
`git ls-remote`. Local `main` (checked out in `wt-integrate-p6a`, clean) was
fast-forwarded to `c931091` and pushed normally (`4fd5faf..c931091`, no
force). Afterwards local `main` == `origin/main` == GitHub == `c931091`.

Before and after, `origin` has 124 heads; the only refs that moved are
`main` and `HEAD`. Unchanged: `p6c-experience-store-v1` (`e4eb260`),
`p6c-experience-failsafe-fix-v1` (`c22a1be`),
`p6b-contract-test-repo-intelligence-v1` (`d040dd9`),
`p6b-yaml-dependency-fix-v1` (`50f4229`),
`p6a-typed-evidence-cache-context-v1` (`f2a5aa8`),
`p5-runner-ownership-v1` (`7861b6b`), `p5-read-authority-v1` (`d7944aa`),
`p5-evidence-reviewability-v1` (`adc8a95`),
`category3-two-team-production-v4c` (`2e7838a`) and
`video-test5-prediction-gauntlet` (`7a79b15`). No branch was deleted or
rewritten; no authoring worktree was modified. `integrate-p6c-v1` is local
only.

No subagents were used. The P3C/P5 paid benchmark was not re-run. No
unrelated backlog was fixed, and no test was edited.

## Carried forward, unchanged by this integration

P6C integration does not fix known technical debt. The register:

1. Nested capsule co-selection / forbidden-over-authorized conflict (live
   instance: the `tools/engineering_runner` ↔ `tools/youtube_fetch` mutual
   forbid).
2. No explicitly named superseded workflow transition.
3. External-runner import-guard breadth.
4. Integration-gate reports are not archived automatically (this directory
   was written by hand).
5. `ResourceUsageRecord` is not migrated to `ExecutionEvidence`.
6. `ContextCache` is not wired into `build_execution_context`.
7. Compressed transient/synthesized artefacts may not always be recoverable.
8. Third-party test dependencies are not checked against requirements
   globally.
9. Dependency-closure truncation does not report reaching its cutoff.
10. Unused `DependencyRelation` enum members.
11. `satisfying/` remains outside the gate-scanned / governed roots.

P6C nonblocking residuals:

* N1. Provenance is not completely re-derived (a stale episode's provenance
  can be edited to read current).
* N2. The decoder-refused work-order fallback.
* N3. A receipt rewrite can fork a second experience identity for one
  attempt (only one is servable).
* N4. `why` prose may mention an unauthorized path even though path
  suggestions are filtered.
* N5. Existence checking for non-`.py` suggestions is weaker.
* N6. An invalid-only corpus abstains under the `stale_only` name.
* N7. Partial token-count naming.
* N8. The replay uses base-commit approximations.

Correction-review residual: the suite's depth-construction recursion test may
be environment-fragile on Windows / Python 3.13. It passed here; the margin is
still environment dependent.

## Programme closure

Real pushed `main` is READY with zero required failures and zero blockers,
from evidence measured on that `main`. The approved P6C-R1 lineage is
integrated, B1 stays closed, no authority regressed, every branch is
preserved, and this record is archived.

**P6C is COMPLETE.**

**The current Company OS AI-efficiency / self-improvement programme is
CLOSED:** P5, P6A, P6B and P6C are complete. There is no P6D, P7 or further
efficiency or optimisation phase.

The next package is **COMPANY OS — POST-EFFICIENCY AUTONOMOUS-COMPANY
ROADMAP**. Its planning question is no longer "how do we optimise AI usage?"
but "what autonomous-company capability should Company OS build next to reach
the target-driven end-state?" (for example target decomposition, target
monitoring, opportunity discovery, self-directed execution, external signal
acquisition, bounded autonomous decision loops, and CEO escalation only when
no legitimate machine path exists). It was not begun in this integration.

This archive commit adds files under this directory only. A commit cannot
record its own test results, so its validation (the required suites, the
suites that read `docs/`, and the gate on the archive commit) is reported
with the integration's closing report, not here.

## Files

| file | what |
|---|---|
| `README.md` | this record |
| `required-suites-merged-tree.json`, `required-suites-post-push-main.json` | the derived set on the merged tree and on real pushed `main` |
| `suite-evidence-integration-branch.json`, `gate-report-integration-branch.{json,txt}` | real branch evidence and gate |
| `suite-evidence-merged-tree-premerge-model.json`, `gate-report-merged-tree-premerge-model.{json,txt}` | the push-decision model |
| `suite-evidence-post-push-main.json`, `gate-report-post-push-main.{json,txt}` | **the proof**: real pushed `main` |
| `branch-scope-guards-on-integration-branch.txt`, `branch-scope-guards-post-push-main.txt` | the three research guards, red on the branch, green on real `main` |
| `full-suite-per-file-merge.json`, `full-suite-failures-merge.txt` | merged-tree full run, per file, and its failing ids |
| `full-suite-failures-parent-main-4fd5faf.txt`, `full-suite-failures-parent-p6c-c22a1be.txt` | the 21 ids re-run on each parent |
| `full-suite-per-file-post-push-main.json`, `full-suite-failures-post-push-main.txt` | the full run on real pushed `main` |
| `full-suite-run.txt` | chunk summary lines for both full runs |
| `experience-invariants-merged-tree.json` | Phase 4 invariant map |
| `b1-probes-merged-tree.txt`, `b1-probes-unfixed-runner.txt`, `b1-and-authority-probes-post-push-main.txt` | B1 probes: merged tree, unfixed control, real `main` |
| `authority-probes-merged-tree.txt` | authority probes |
| `recursion-fixture-classification.txt` | the recursion-depth fixture, four runs |
| `import-boundaries-merged-tree.json` | AST and text import scan |
| `knowledge-separation-merged-tree.json` | KnowledgeStore snapshot around real capture/suggest |
| `replay-reproduction-merged-tree.json`, `verify-evidence-merged-tree.txt` | replay re-run and corpus re-digest |
| `focused-validation-merged-tree.json` | focused suites, no-subagent and protected-surface selections |
| `ref-preservation.txt` | `git ls-remote` before and after the push |
| `probes/` | the probe and evidence-building scripts this session wrote |

The probes run from the repository root, for example
`python -m pytest -c pytest.ini --rootdir . docs/evidence/company_os_p6c_production_integration/probes/b1_probes.py`.
