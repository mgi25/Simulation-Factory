# P6B — production integration record

P6B (exact contract/test dependency discovery and repository intelligence),
with its one independently reviewed correction, integrated into `main` on
2026-09-25. This directory is append-only. It does not rewrite
`docs/evidence/company_os_p6b_contract_test_repo_intelligence/`, which stays
exactly as the P6B branch archived it.

## The SHAs

| | |
|---|---|
| starting `main` (first parent of the merge) | `bf0dd1f069b66e1914778796ba5a500d7e048eff` |
| approved original P6B | `d040dd9cfe64e4d59333afd01d08dd8e84496190` (`p6b-contract-test-repo-intelligence-v1`) |
| approved correction, the integration candidate | `50f42297849364ab6498f894a964d3642cbd9e65` (`p6b-yaml-dependency-fix-v1`) |
| merge base | `39fbd44ee7d9c755ba2059b5ab9a467e9c399f30` |
| integration merge (`--no-ff`, branch `integrate-p6b-v1`) | `5da27cfb723d059d46c560e2d92e38681ba1ce02` |
| merge tree | `a3336f0a3f61d786d71f79fe8cdb9c84a7c94e88` |
| `main` after the push | `5da27cf` (this archive commit lands on top of it) |

Review lineage: the full independent P6B review returned CHANGES_REQUIRED with
exactly one blocker (undeclared PyYAML in `tests/test_company_review_separation.py`,
a suite P6B makes required). The correction `50f4229` was reviewed
independently and returned PASS.

## Topology and overlap

Recomputed after a fresh fetch, not copied from the brief.

| | |
|---|---|
| `50f4229^` | `d040dd9` (exactly 1 commit ahead) |
| `main` ahead of base | 15 commits (Category 3 Test #2) |
| P6B lineage ahead of base | 15 commits (14 P6B + 1 correction) |
| files changed on `main` since base | 216 |
| files changed on the P6B lineage | 38 |
| overlap | **0** |

`git merge-tree --write-tree origin/main 50f4229` returned the single tree
`a3336f0` with no conflicted paths, so the merge was known clean before it ran.
The merge produced exactly that tree.

Structural checks on the merge:

* The first parent is `bf0dd1f` and the second is `50f4229`. `bf0dd1f`,
  `d040dd9`, `50f4229` and `39fbd44` are all ancestors. `39fbd44..5da27cf` is
  31 commits: 15 + 15 + the merge.
* `git diff --name-status bf0dd1f 5da27cf` is identical to
  `git diff --name-status 39fbd44 50f4229`.
* Every P6B path is byte-equal to `50f4229`. Every main-only path is
  byte-equal to `bf0dd1f`.
* 0 deletions against either parent. No P5, P6A or video evidence and no
  `satisfying/` or `godot/` path is touched. The merge adds only P6B's own
  code, tests, capsule seed and evidence directory.
* The merged `tests/test_company_review_separation.py` equals `50f4229` and
  contains no `import yaml`.

## Bookkeeping corrections (append-only; old evidence is not rewritten)

1. **The original P6B implementation report said 32 files. The real diff is
   37.** `git diff --shortstat 39fbd44 d040dd9` gives *37 files changed, 8165
   insertions(+), 245 deletions(-)*. The 32 figure appears in the
   implementation report only, not in the archived evidence, so nothing in the
   repository needs amending.
2. **The production candidate changes 38 files from the P6B base, not 37.** The
   YAML correction modifies `tests/test_company_review_separation.py`, which the
   original P6B did not touch. `git diff --shortstat 39fbd44 50f4229` gives
   *38 files changed, 8175 insertions(+), 249 deletions(-)*.

## Repository intelligence, recomputed on the merged tree

`repository-intelligence-merged-tree.json`. Both graphs were built twice and
matched byte for byte.

| | merged tree `5da27cf` | P6B tip `50f4229` |
|---|---:|---:|
| gate graph modules | 746 | 735 |
| test modules | 166 | 160 |
| direct edges | 5000 | 4996 |
| `TYPE_CHECKING`-only edges (kept separate) | 15 | 15 |
| unresolved (dynamic imports, named and never edges) | 22 | 22 |
| parse failures | 0 | 0 |
| graph fingerprint | `98bb72f8831d6581` | `e43dbbd4d28abac7` |
| runner map modules | 536 | 525 |
| runner modules with a direct test | 174 | 173 |
| runner module→test edges | 446 | 445 |
| runner `production_dependents` entries | 248 | 248 |

**The delta is exactly the main-only lineage.** It adds 11 modules (5
`tools/*_lab.py` / `*_screen.py` Category 3 scripts and 6 Category 3 test
modules) and exactly 4 edges, all from Category 3 tests into production code:

* `tests/test_multiplying_shell.py -> tools/two_team_phase4a_lab.py`
* `tests/test_multiplying_shell_audio.py -> audio/__init__.py`
* `tests/test_multiplying_shell_audio.py -> audio/loudness.py`
* `tests/test_multiplying_shell_audio.py -> audio/wav_io.py`

No edge is removed. No new edge touches a Company OS module, so none can make
a suite required. The 22 unresolved dynamic imports and the capsule audit's
`declared_not_observed` findings are identical to the P6B tip.

Why these numbers differ from P6B's own archive: P6B's
`dependency-graph-summary.json` (4993 edges, fingerprint `424061ebf85dae78`)
was written at `5600631`, before later P6B commits (e.g. `93d9bd9`
re-exporting from the runner facade) added edges. The P6B tip itself measures
4996 edges. The archive is a snapshot, not an error.

Semantics are unchanged. An edge is a static import relationship, never a
coverage claim, and `DependencyRelation` still has exactly `direct_static`,
`transitive_static`, `declared_contract`, `declared_not_observed`,
`observed_not_declared` and `unresolved`. On the merged tree,
`tests/test_company_gate_suite_requirements.py` → `company/integration/suites.py`
is still `transitive_static`, not direct. The probe counts
(direct/transitive tests reaching six named modules) are identical to the P6B
tip.

**Capsule audit:** 23 capsules, 20 own Python, 0 without a static witness.

## Governed production subsystems

The packages are derived from the graph, not hard-coded (no package name
appears in `company/integration/*.py`).

| package | modules | owner (in force) | `owns_paths` |
|---|---:|---|---|
| `tools/engineering_runner` | 19 | `company-external-engineering-runner` | `["tools/engineering_runner"]` |
| `tools/youtube_fetch` | 9 | `company-youtube-fetch-client` | `["tools/youtube_fetch"]` |

`architecture.governed_subsystem_ownership` is in `REQUIRED_CHECKS` and passes
on the merge. Ownership was not broadened. Each capsule forbids the other's
package in `must_not_modify`. That mutual forbid is carried-forward finding 1;
it predates this integration and does not block it.

## Required suites

`required-suites-merged-tree.json`, from the real resolver on the merged tree:
**45 suites, fingerprint `72502df3cfb3cbb7`, `unresolved == []`**, and a second
resolve gave the same result. That is identical to the P6B tip (same names,
same fingerprint).

| origin | suites |
|---|---:|
| canonical | 11 |
| capsule_contract | 33 |
| dependency_observed | 39 |
| change_scope (unscoped run) | 0 |

The 11 formerly undeclared Company OS suites are all required, each through
`dependency_observed`. They are exactly the 11 suites whose only origin is
`dependency_observed`, and `undeclared_company_os_suites` is empty.

Change scope still widens identity without narrowing the set.
`--changed-path company/integration/suites.py` gives 45 suites, 2 of them
carrying `change_scope`, with fingerprint `f718e132860b4d82`. A production path
(`race2/race.py`) leaves the fingerprint at `72502df3cfb3cbb7`. Leaving out
`graph=` still yields an unresolved set.

## Suite runs

Every required suite was run on the merged tree in the canonical `.venv`,
Python 3.13.0, where **PyYAML is not installed** (`import yaml` fails). Nothing
was installed.

The three `test_this_branch_changed_no_race_fight_or_v30_code` guards diff
`origin/main...HEAD`, so they are red on any branch that changes `tools/` until
`main` is the merge. So the runs were taken three ways:

| where | `origin/main` | evidence file | result |
|---|---|---|---|
| the real integration branch, three research suites only | `bf0dd1f` | `suite-evidence-integration-branch.json` | each fails exactly its guard (80/1, 117/1, 121/1), listing P6B's three `M tools/engineering_runner/*` files — `branch-scope-guards-on-integration-branch.txt` |
| a local clone at `5da27cf` with GitHub-faithful `origin/*` refs and `origin/main` repointed to the merge (a model of post-push `main`; no real ref touched) | `5da27cf` (model) | `suite-evidence-merged-tree.json` | **45/45 suites green, 3070 tests, 0 failed, 1 skipped** |
| **real pushed `main`** | `5da27cf` (real) | `suite-evidence-post-push-main.json` | the three research suites 81/81, 118/118, 122/122, and review-separation 32/32. **The three guards self-healed on real `main`.** The other 41 results are the merged-tree runs of the same tree. |

`tests/test_company_review_separation.py` collected and passed (32/32) in
`.venv` without PyYAML on both the model and real `main`.

**Focused P6B validation** (`focused-property-tests.json`, per test from junit,
all passed):

* 28 graph-property tests: relative imports, `from X import y`, direct vs
  transitive, cycle termination, dynamic imports left unresolved, no filename
  heuristic, dependency-observed origin, the bounded witness set, governed
  subsystems, `change_impact` on the real change set, bounded impact slices.
* 30 no-subagent tests.
* 34 protected-surface tests.
* 19 boundary-guard tests.
* 20 authority tests, including `test_change_impact_creates_no_authority`.

Focused suites with their counts: dependency_graph 54, gate_suite_requirements
46, integration_gate 89, os_capsules 68, review_separation 32,
external_engineering_runner 185, company_external_engineering_runner 64,
engineering_execution 207, read_authority 34, context_assembly 9,
context_expansion 17, typed_evidence_context 59, evidence_review 25,
delegation 152, session_execution 48, runtime 22.

## Full-suite regression

On the merged tree, in the main-shaped clone, split into chunks (a single run
dies around 30 min here):

| chunk | failed | passed | skipped |
|---|---:|---:|---:|
| 45 required suites | 0 | 3069 | 1 |
| Category 3 (12 files) | 0 | 907 | 1 |
| other A (54 files) | 13 | 1410 | 104 |
| other B (55 files) | 5 | 1553 | 335 |
| **total, 7398 tests** | **18** | **6939** | **441** |

There were **0 collection errors**. The former PyYAML collection error is gone,
and this time that is not an environment effect: PyYAML is absent from `.venv`.

**Classification by node id.** The 18 merged-tree failures
(`full-suite-failures-merge.txt`) were re-run as exact node ids on both parents.
All 18 fail identically on `bf0dd1f` and on `50f4229`:

* 12 stale race branch-scope guards: `v30_stage`, `v301_stage`, `v311_track`
  ×2, `v321_geometry`, `v32_final` ×6, `v33_bookends`.
* 5 sloped-world failures on gitignored render output (`sloped_v251_world` ×4,
  `sloped_v252_world` ×1).
* 1 neon/Godot (`test_neon_proof`).

**Integration-introduced failures: 0.** This is `main`'s steady-state
fingerprint of 18 failed / 441 skipped.

## Architecture boundaries

Scanned on the merged tree with both an AST scan and a raw-text scan, because
P6B found the two can disagree. Positive controls: `company → ai_platform` finds
186 by AST and 186 by text; `tests → tools.engineering_runner` finds 52 by AST
and 54 by text.

| boundary | AST | raw text |
|---|---:|---:|
| Company OS (`company`, `ai_platform`, `knowledge`, `intelligence`) → `tools.engineering_runner` | 0 | 0 |
| `tools/engineering_runner` → Company OS | 0 | 0 |
| `tools/youtube_fetch` → Company OS | 0 | 0 |
| any production root, `satisfying/` included → Company OS | 0 | 0 |

The gate's `architecture.production_does_not_import_company_os` passes, as do
the suites' own guards (`test_company_os_does_not_import_the_external_runner`,
`test_the_runner_does_not_import_the_capsule_layer`,
`test_the_runner_does_not_even_write_the_control_plane_import_lines`, and the
text-level guard in `test_company_session_execution.py`).

**No new authority.** The 1822 added production lines contain no subprocess,
file-write, network, git, publish, upload or deploy call; the only hits are
four docstring mentions of "subprocess". `authorization.py`, `workspace.py` and
`runner.py` are untouched. The new `_change_impact_block` in `briefs.py` is
explicitly advisory text. The gate still reports
`production.integration_remains_disabled`,
`production.no_publishing_capability`,
`execution.read_authority_fails_closed`,
`execution.write_authority_fails_closed` and
`execution.no_subagent_runtime_lock` as PASS.

## Integration gate

`python -m company.integration check --repo-root . --suite-evidence <file>`, with
no `--state-dir` (as in P6A):

| report | source | result |
|---|---|---|
| `gate-report-integration-branch.*` | `integrate-p6b-v1` @ `5da27cf`, `origin/main` = `bf0dd1f` | **BLOCKED**. The sole blocker is `health.required_suites_pass`, over the three guard-bearing research suites. This is expected by construction, not a defect. |
| `gate-report-merged-tree-premerge-model.*` | `5da27cf`, `origin/main` modelled as the merge | **READY**, 37 pass / 0 fail / 2 unknown, 0 blockers |
| `gate-report-post-push-main.*` | real `main` @ `5da27cf` | **READY**, 37 pass / 0 fail / 2 unknown, 0 blockers |

Policy v1: 35 required and 4 advisory checks. All 35 required checks pass,
including `health.required_suites_pass` and
`architecture.governed_subsystem_ownership`. The 2 unknowns are both advisory
(`executive.decision_queue_preserves_source_refs`,
`workforce.capability_gaps_visible`) and are unknown only because no company
state directory was supplied; policy permits that. The modelled report was
used only to decide the push. The proof is the post-push report.

## Push and preservation

`origin/main` was re-fetched immediately before the push and was still
`bf0dd1f`, the merge's first parent. Local `main` was fast-forwarded to
`5da27cf` and pushed normally (`bf0dd1f..5da27cf`, no force). Afterwards local
`main` == `origin/main` == `5da27cf`.

Before and after the push, `origin` has 122 heads. The only ref that moved is
`main` (and `HEAD`). All of these are unchanged:
`p6b-contract-test-repo-intelligence-v1` (`d040dd9`),
`p6b-yaml-dependency-fix-v1` (`50f4229`),
`p6a-typed-evidence-cache-context-v1` (`f2a5aa8`),
`p5-evidence-reviewability-v1` (`adc8a95`), `p5-read-authority-v1` (`d7944aa`),
`p5-runner-ownership-v1` (`7861b6b`) and
`category3-two-team-production-v4c` (`2e7838a`). No branch was deleted or
rewritten, and `integrate-p6b-v1` is local only.

No subagents were used, the P3C/P5 paid benchmark was not re-run, and P6C was
not started.

## Carried forward, unchanged by this integration

1. Nested capsule co-selection / forbidden-over-authorized conflict. The live
   instance is the `tools/engineering_runner` ↔ `tools/youtube_fetch` mutual
   forbid.
2. There is no explicitly named superseded workflow state.
3. External-runner import-guard breadth.
4. Gate reports are not archived automatically (this directory was written by
   hand).
5. `ResourceUsageRecord` is not migrated to `ExecutionEvidence`.
6. `ContextCache` is not wired into `build_execution_context`.
7. Compressed transient/synthesized artefacts may not be recoverable.
8. Test third-party dependencies are not checked against requirements
   globally. PyYAML 6.0.1 sits in the ambient system Python here, which is how
   the review-separation import went unnoticed.
9. The closure-expansion cutoff does not report whether it was reached.
10. Unused `DependencyRelation` members.
11. `satisfying/` (43 modules) is outside the gate's scanned roots. Confirmed
    unscanned on the merged tree, and deliberately not added.

**Next work package: P6C — experience store.** Not begun.
