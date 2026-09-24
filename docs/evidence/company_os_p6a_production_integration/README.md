# P6A — production integration record

Append-only. This record describes one event: the merge of the independently
reviewed P6A branch into canonical `main`, and the validation run against the
**actual merged tree** rather than against P6A's own pre-merge simulation.

It does not replace, amend or re-open
`docs/evidence/company_os_p6a_typed_evidence_cache_context/`. That directory is
P6A's own development and review evidence and stands unchanged; this one only
references it.

---

## 1. Identities

| | |
|---|---|
| pre-integration `main` | `6cf59c95843c05c552332c81687c8f55df1f2331` |
| approved P6A branch | `p6a-typed-evidence-cache-context-v1` |
| approved P6A tip | `f2a5aa80e89c4b8dff98673d59473e717cb64d83` |
| integration branch | `integrate-p6a-v1` |
| **integration merge** | **`5e91cefc59852b8736148f5722b83428eb05c496`** |
| merge parent 1 (main) | `6cf59c95843c05c552332c81687c8f55df1f2331` |
| merge parent 2 (P6A) | `f2a5aa80e89c4b8dff98673d59473e717cb64d83` |
| merge base | `6cf59c95843c05c552332c81687c8f55df1f2331` |
| final `origin/main` | `5e91cefc59852b8736148f5722b83428eb05c496` |

Preflight: P6A was **7 ahead, 0 behind** `main`, and the merge base *was* main's
tip, so the two histories had not diverged at all. There was no overlap to
analyse and **no conflict arose**. The merge used `--no-ff`: P6A was neither
squashed nor rebased, and `f2a5aa8` is a literal parent of `5e91cef`.

`main` was advanced by **fast-forward** onto the validated merge commit and
pushed normally. No force push. No branch was deleted: 120 remote heads before,
120 after, and `refs/heads/main` was the only ref whose SHA moved.

### The seven P6A commits, all ancestors of `main`

```
f2a5aa8  P6A: derive the evidence README's numbers instead of copying them
4b18b24  P6A: make a capsule's disappearance change the set identity
001f9d0  P6A: record both gate runs, and demonstrate the self-heal
6271e1a  P6A: close the two fail-open paths the independent review reproduced
b8bf404  P6A: report the Company OS tests no capsule declares
b559306  P6A: derive the gate's required suites; typed evidence and cache-stab...
3f8da0a  baseline: correct two stale research capsule owns_paths expectations
```

### Tree composition

`git diff f2a5aa8 5e91cef` is **empty**: because the merge base was main's tip,
the merged tree is byte-identical to the approved P6A tree. Against
pre-integration main the merge is **14 added, 15 modified, 0 deleted,
0 renamed**, and `git rev-list --count 6cf59c9 ^5e91cef` is **0** — no commit
of main's history was lost. No P6A evidence file disappeared, no P5 evidence or
history was rewritten, and no Category 3 / video work was touched.

---

## 2. Derived required suites

Resolved from the merged repository with P6A's own resolver, not copied from
P6A's evidence:

```
python -m company.integration required-suites --repo-root . --json
```

| | |
|---|---|
| required-suite fingerprint | **`aa3d963058e460bd`** |
| required suites | **32** |
| `unresolved` | `[]` — fully **RESOLVED** (exit 0) |
| derived from | 22 capsules |
| origins | 11 canonical · 31 declared by a capsule contract in force · 0 in change scope |

The same fingerprint was produced independently in three places: the
integration worktree, the main-shaped clone, and the real pushed `main`.

The canonical list is **11** and remains only the floor; capsule contracts
widen it to 32. Change scope was verified to widen and never narrow:

| change scope | required | fingerprint |
|---|---|---|
| none | 32 | `aa3d963058e460bd` |
| `tools/engineering_runner/runner.py` | 32 | `5fc09531fb7ffdc2` |
| `company/runtime/context_cache.py` | 32 | `a4a7c21a894dbe63` |
| `race2/race.py` (a production path) | 32 | `aa3d963058e460bd` |

A production path leaves the set *and* its identity untouched — the Company OS
gate is not widened by production changes. A Company OS path changes the set
identity (the origin set changes) without ever shrinking the membership.

---

## 3. Required-suite results

Every one of the 32 was run individually and the evidence below was built from
those runs — `suite-results-merged-tree.json` and
`suite-results-integration-branch.json`.

| Suite | selected | merged tree | integration branch |
|---|---|---|---|
| `tests/test_company_analytics.py` | 160 | pass | pass |
| `tests/test_company_context_assembly.py` | 9 | pass | pass |
| `tests/test_company_dashboard.py` | 32 | pass | pass |
| `tests/test_company_delegation.py` | 152 | pass | pass |
| `tests/test_company_efficiency.py` | 69 | pass | pass |
| `tests/test_company_engineering_execution.py` | 207 | pass | pass |
| `tests/test_company_evidence_review.py` | 25 | pass | pass |
| `tests/test_company_execution_transport.py` | 14 | pass | pass |
| `tests/test_company_external_engineering_runner.py` | 64 | pass | pass |
| `tests/test_company_finance.py` | 123 | pass | pass |
| `tests/test_company_finance_usage_cost.py` | 48 | pass | pass |
| `tests/test_company_gate_suite_requirements.py` | 45 | pass | pass |
| `tests/test_company_integration_gate.py` | 89 | pass | pass |
| `tests/test_company_org_intelligence.py` | 119 | pass | pass |
| `tests/test_company_os_ai_platform.py` | 46 | pass | pass |
| `tests/test_company_os_capsules.py` | 68 | pass | pass |
| `tests/test_company_os_knowledge.py` | 26 | pass | pass |
| `tests/test_company_os_research.py` | 81 | pass | FAIL (1) |
| `tests/test_company_os_research_batches.py` | 118 | pass | FAIL (1) |
| `tests/test_company_os_research_ingestion.py` | 122 | pass | FAIL (1) |
| `tests/test_company_read_authority.py` | 34 | pass | pass |
| `tests/test_company_runtime.py` | 22 | pass | pass |
| `tests/test_company_typed_evidence_context.py` | 59 | pass | pass |
| `tests/test_company_workforce.py` | 93 | pass | pass |
| `tests/test_company_youtube_connectivity.py` | 29 | pass | pass |
| `tests/test_company_youtube_live_findings.py` | 55 | pass | pass |
| `tests/test_company_youtube_studio_ingestion.py` | 142 | pass | pass |
| `tests/test_engineering_runner_execution_context.py` | 40 | pass | pass |
| `tests/test_engineering_runner_exploration_report.py` | 19 | pass | pass |
| `tests/test_engineering_runner_exploration_telemetry.py` | 25 | pass | pass |
| `tests/test_engineering_runner_repo_map.py` | 25 | pass | pass |
| `tests/test_external_engineering_runner.py` | 185 | pass | pass |

**Merged tree: 32/32 green. Integration branch: 29/32.**

The three-suite difference is one test,
`test_this_branch_changed_no_race_fight_or_v30_code`, present in each of the
three research suites. It runs `git diff --name-status origin/main...HEAD` and
refuses any change under a declared production root. `tools/` is such a root,
and P6A edits `tools/engineering_runner/controlplane.py` and
`tools/engineering_runner/runner.py`. So on any branch that has not yet become
`main` it fails **by construction**, and it is the only assertion that does.

That self-heal is **demonstrated on the real thing, not simulated**. After the
fast-forward, `origin/main` *is* the merge commit, the diff is empty, and in the
live worktree:

```
tests/test_company_os_research.py             81 passed
tests/test_company_os_research_batches.py    118 passed
tests/test_company_os_research_ingestion.py  122 passed
+ test_company_gate_suite_requirements.py and test_company_typed_evidence_context.py
                                       ->  425 passed across all five
```

Each is exactly **+1 pass and -1 failure** against the branch run: the guard,
and nothing else.

### The two repaired owns_paths tests

`3f8da0a` corrects two stale research-capsule expectations. Run on
pre-integration `main` (`6cf59c9`) they **fail**; run on the merge they
**pass**:

```
tests/test_company_os_research_batches.py::test_the_research_capsule_stays_within_budget_with_the_batch_layer_in_it
tests/test_company_os_research_ingestion.py::test_the_research_capsule_loads_and_stays_within_budget
```

---

## 4. Full-suite regression

`pytest --continue-on-collection-errors` over the whole repository, both trees,
on the same machine:

| tree | result | wall |
|---|---|---|
| merge `5e91cef` | **21 failed, 6305 passed, 441 skipped** | 1:28:11 |
| pre-integration main `6cf59c9` | **20 failed, 6184 passed, 441 skipped** | 1:27:58 |

Judged by node-id set, never by count:

| | |
|---|---|
| in merge, not in baseline | **3** - the three branch-scope guards, all proven green on the merged/main-shaped tree |
| in baseline, not in merge | **2** - the `owns_paths` repairs |
| inherited, unchanged | **18** |

**Zero integration-introduced failures.** The three that appear are the
structural, self-healing guard described above; they are green on `main`.

The 18 inherited failures are stale branch-scope and artefact guards in
`test_neon_proof`, `test_race2_*` and `test_sloped_v25*` - see
`full-suite-failures-baseline.txt` and `full-suite-failures-merge.txt`. They
fail identically on both parents and are out of scope for this package.

### The undeclared yaml dependency - NOT fixed, and NOT masked by this package

`tests/test_company_review_separation.py` imports `yaml`, which is declared in
no requirements file. **No collection error occurred in either run here**, for
one reason only: the ambient interpreter already has PyYAML installed. Nothing
was installed to produce that result, and the finding is untouched - `yaml` is
still undeclared, and in a clean environment a bare `pytest` still aborts during
collection. Recorded as carried-forward finding 8, not as resolved.

---

## 5. Integration gate on the actual merged tree

Fresh evidence, fresh report, against the real merge. P6A's simulated
post-merge report was **not** reused as the proof.

```
python -m company.integration check --repo-root . \
  --suite-evidence <the 32 real runs above>
```

| | |
|---|---|
| readiness | **READY** (exit 0) |
| report | `integration-readiness-2026-09-24-4e0bfa29a7bc23c7` |
| source commit | `5e91cefc59852b8736148f5722b83428eb05c496` |
| policy | v1: 34 required, 4 advisory |
| checks | **35 pass, 0 fail, 3 unknown, 0 not_applicable** |
| REQUIRED blockers | **none** |
| `health.required_suites_pass` | **PASS** |

The `health.required_suites_pass` detail, verbatim:

> all 32 required suites reported passing, oldest run 0 day(s) ago; required-set
> aa3d963058e460bd (11 canonical, 31 declared by a capsule contract in force,
> 0 in change scope), derived from 22 capsule(s)

The three UNKNOWNs are all **advisory** and all genuinely state-directory
dependent - no `--state-dir` was supplied, so the gate reports them untested
rather than satisfied, which is the designed behaviour:

- `executive.decision_queue_preserves_source_refs` (advisory)
- `health.production_failures_separated` (advisory)
- `workforce.capability_gaps_visible` (advisory)

Full report: `gate-report-merged-tree.txt` and `gate-report-merged-tree.json`.

The report states the technical gate conditions only. It does **not** authorize
wiring Company OS into production; `authorizes_production_integration` is
`false`, and that remains a separate CEO decision.

---

## 6. P6A safety properties, verified on the merged tree

| property | result |
|---|---|
| canonical 11-suite list remains only the floor | PASS - 11 canonical, set resolves to 32 |
| capsule contracts widen the required set | PASS - 31 of 32 carry a `capsule_contract` origin |
| change scope can only widen, never narrow | PASS - no scope produced fewer than 32 |
| unresolved derivation blocks readiness | PASS - `resolve_required_suites` appends to `unresolved` for a `None`, empty or structurally broken index, holding `health.required_suites_pass` at `unknown` |
| Company OS gate spawns no pytest or process itself | PASS - no `import subprocess` anywhere in `company/`; `test_deriving_the_set_spawns_no_process` green |
| external runner queries required suites across the CLI boundary | PASS - `ControlPlane.required_suites` shells `python -m company.integration required-suites --json`, and refuses a non-zero exit or any `unresolved` entry rather than accepting a short list |
| production does not import Company OS | PASS - gate check `architecture.production_does_not_import_company_os`; no `from company` or `import company` in `satisfying/`, `rendering/`, `physics/` |
| Company OS does not improperly import the external runner | PASS - no `from tools` or `import tools` statement in `company/`; the only mentions are prose in docstrings |
| no-subagent remains locked | PASS - gate check `execution.no_subagent_runtime_lock`; `nested_agent_spawning` refused in `company/validation/no_subagents.py`, `bootstrap.py`, `contracts.py`, `probes.py` |
| no merge/deploy/publish authority introduced | PASS - the merge adds no such call site and no new `subprocess` use |
| protected surfaces remain protected | PASS - `production.integration_remains_disabled`, `production.no_automatic_production_mutation`, `production.no_production_delete_authority`, `production.no_publishing_capability`: all required, all PASS |

---

## 7. What P6A does NOT establish

Stated here so that no later reader infers it from the word "efficiency"
elsewhere in this repository. P6A establishes **none** of:

- provider token savings;
- provider monetary savings;
- subscription quota savings;
- whole-task efficiency improvement.

It establishes derived required-suite evidence, typed execution evidence, a
digest-validated context cache, and the boundary behaviours listed in section 6.

---

## 8. Carried forward, deliberately not fixed here

1. nested capsule co-selection / forbidden-over-authorized conflict;
2. no explicitly named superseded workflow state;
3. external-runner import-guard breadth;
4. gate reports are not archived automatically;
5. `ResourceUsageRecord` not yet migrated to `ExecutionEvidence`;
6. `ContextCache` not yet wired into `build_execution_context`;
7. 11 Company OS suites are declared by no capsule - `required-suites.json`
   names them under `undeclared_company_os_suites`; the list changes no verdict;
8. undeclared `yaml` test dependency / collection error (see section 4);
9. the change-scope path has little operational effect today - everything in
   force is already required - and the runner does not yet feed its own git diff
   into it;
10. compressed synthesized or transient artefacts are not necessarily
    recoverable;
11. `capsule.test` declarations are not verified against actual test or module
    dependencies.

**Item 11 is the P6B target.** It was not begun in this session.

---

## 9. Next work package

**P6B - exact contract / test dependency discovery + repository intelligence.**
