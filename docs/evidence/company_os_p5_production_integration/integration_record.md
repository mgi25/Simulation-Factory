# P5 production integration — integration record

CEO-authorized integration of the independently approved P5 lineage into `main`.
This record does not restate or replace earlier P5 evidence; it points back to it.

## Preflight (Phase 0)

Re-fetched from origin before integrating. Observed:

| item | value |
| --- | --- |
| original `main` (as stated in the CEO package) | `d2a30027aeaf044c3e9d03ef961b8f8331a16140` |
| `origin/main` actually integrated from | `d2a30027aeaf044c3e9d03ef961b8f8331a16140` (unchanged) |
| approved P5 candidate `p5-runner-ownership-v1` | `7861b6b42f7765de988dc122860923fb519ebd5a` (unchanged) |
| merge base | `65df08a3e22d692d2783ab6004ce6f3d4046f54e` |
| ahead/behind from base | main +10, P5 +104 |
| main-only changed files | 65 |
| candidate-only changed files | 88 |
| overlapping changed files | **0** |

The 10 main-only commits are Category 3 / tile-escape work: `satisfying/`,
`godot/`, `docs/validation/category3_tile_escape/` and six `tests/test_tile_escape*.py`
files. The 104 candidate-only commits are Company OS and external-runner work.
No shared test infrastructure (`conftest.py`, `pytest.ini`, `pyproject.toml`)
was touched by either side.

## Merge (Phase 1)

Integration branch `integrate-p5-v1` created from `origin/main`, then:

    git merge --no-ff p5-runner-ownership-v1

No squash, no rebase, no P5 commit SHA rewritten.

**Conflict result: none.** Git reported zero conflicts, as the zero-overlap
preflight predicted.

| item | value |
| --- | --- |
| integration merge commit | `03e43362c8b9cd0169a3f204f16702090f936387` |
| first parent | `d2a30027aeaf044c3e9d03ef961b8f8331a16140` (main) |
| second parent | `7861b6b42f7765de988dc122860923fb519ebd5a` (P5) |

## Structural integrity (Phase 2)

Both parent histories survive in full:

- all 10 main-side commits are ancestors of the merge;
- all 104 P5-side commits are ancestors of the merge;
- `p5-runner-ownership-v1` still points at `7861b6b`, unrewritten.

The merged tree is exactly the union of the two sides, proven both ways:

- `diff(main -> merge)` is identical to `diff(base -> P5)`;
- `diff(P5 -> merge)` is identical to `diff(base -> main)`.

No file present on either parent is absent from the merge. Tree counts compose
exactly: `tests/` 150 (base) + 6 (Category 3) + 2 (P5) = 158. Every full
40-character commit SHA referenced in the P5 evidence still resolves.

## Post-merge validation (Phase 3)

Full suite on the merged tree, system Python 3.13.0 / pytest 8.4.2:

    23 failed, 6181 passed, 441 skipped in 4704.61s (1:18:24)

Targeted suites, all on the merged tree:

| group | suites | passed | failed |
| --- | --- | --- | --- |
| gate-required Company OS suites | 11 | 791 | 0 |
| runner / read-authority / evidence-review / delegation | 16 | 1011 | 0 |
| Category 3 tile-escape (main-side) | 6 | 331 | 0 |
| remaining governance + research | 6 | 586 | 5 |

### Failure attribution

All 23 failures were replayed at the two parent SHAs. **Zero were introduced by
the integration.**

- **18 inherited from `main` (`d2a3002`)** — `test_neon_proof`, `test_race2_v30*`,
  `test_race2_v31*`, `test_race2_v32*`, `test_race2_v33*`, `test_sloped_v251*`,
  `test_sloped_v252*`. Replayed at `d2a3002`: 18 failed, identically. These are
  the known stale branch-scope guards.
- **5 inherited from the approved P5 candidate (`7861b6b`)** — replayed at
  `7861b6b`: 5 failed, identically; replayed at `d2a3002`: 5 passed. See below.

### The 5 candidate-inherited failures

Three are branch-scope guards, `test_this_branch_changed_no_race_fight_or_v30_code`
in `test_company_os_research.py`, `test_company_os_research_batches.py` and
`test_company_os_research_ingestion.py`. They diff `origin/main...HEAD` and refuse
changes under a production root; `tools/` is a declared production root, so the
runner work trips them by construction. Once `origin/main` is the merge commit
that diff is empty and these pass again.

Two do **not** self-heal and are carried forward as a correctness item:

- `test_company_os_research_ingestion.py::test_the_research_capsule_loads_and_stays_within_budget`
- `test_company_os_research_batches.py::test_the_research_capsule_stays_within_budget_with_the_batch_layer_in_it`

Both fail on the same single assertion. The candidate widened
`knowledge/company_os/capsules/seeds/company-research-intelligence.json`
`owns_paths` from `["intelligence/research"]` to
`["intelligence/__init__.py", "intelligence/research"]` and left two test
expectations at the old value. The capsule *budget* assertion in both tests
passes; only the `owns_paths` tuple comparison fails. Neither suite is in
`REQUIRED_SUITES`, so the integration gate is unaffected.

Not fixed here: the CEO package forbids altering the approved candidate and
forbids unrelated correctness fixes during integration.

### Integration gate

`python -m company.integration check` on the merged tree, with supplied suite
evidence for all 11 required suites:

    PRODUCTION INTEGRATION READINESS: READY
    policy v1: 34 required, 4 advisory
    checks 35 pass, 0 fail, 3 unknown, 0 not_applicable
    BLOCKERS none

The 3 unknowns are all advisory and all state-directory dependent
(`executive.decision_queue_preserves_source_refs`,
`health.production_failures_separated`, `workforce.capability_gaps_visible`).

## Approved P5 claims after the merge (Phase 4)

| claim | evidence on the merged tree |
| --- | --- |
| adaptive economy routing present | `company/efficiency/strategy.py::select_strategy`; `test_company_efficiency.py` 69 passed |
| read authority fingerprinted / fail-closed | `company/runtime/authority.py` packet+contract fingerprints; gate `execution.read_authority_fails_closed` PASS; `test_company_read_authority.py` 34 passed, incl. `test_a_work_order_with_no_declared_read_scope_grants_none` and `test_stripping_the_read_fields_forfeits_authority_rather_than_forging_it` |
| evidence review surface narrow | `company-evidence-review` owns only `docs/evidence/reviews`, may write only `*.md` / `*.json` there |
| external runner owns only `tools/engineering_runner` | `company-external-engineering-runner.owns_paths` is exactly `["tools/engineering_runner"]` |
| Company OS does not import the runner | no import of `engineering_runner` anywhere in `company/`, `ai_platform/`, `knowledge/`, `intelligence/` — only prose references |
| production does not import Company OS | gate `architecture.production_does_not_import_company_os` PASS |
| no-subagent invariant holds | `company/validation/no_subagents.py`; gate `execution.no_subagent_runtime_lock` PASS |
| no merge/deploy/publish authority created | gate `production.no_publishing_capability`, `production.no_automatic_production_mutation`, `production.no_production_delete_authority`, `production.integration_remains_disabled` all PASS; no `subprocess` import in `company/` or `ai_platform/` |

### Benchmark claim — scope unchanged

> P5 reduces provider-equivalent monetary cost for the matched workload while
> preserving accepted quality.

Token savings remain **NOT ESTABLISHED**. Subscription quota savings remain
**NOT MEASURED**. The paid P3C-vs-P5 benchmark was not rerun for this
integration.

## Deferred findings carried forward (Phase 5)

Not fixed during integration, and not to be forgotten:

1. **Co-selected capsule nested-scope conflict.** A work order co-selecting
   `company-external-engineering-runner` with any of the seven capsules that
   forbid `tools/**` inherits the broader rule, and forbidden wins. Recorded in
   that capsule's own `risks`. **Preserve this as a Company OS correctness item —
   it did not block P5, which is not the same as being resolved.**
2. **No named superseded lifecycle state.** A capsule or record that has been
   replaced has no lifecycle state saying so.
3. **Recursive import-guard coverage is narrower than the boundary it defends.**
4. **Historical gate reports are not archived**, so a past verdict cannot be
   re-read.
5. *(new, found during this integration)* **Stale `owns_paths` expectation in two
   research suites**, described under Phase 3 above. Single root cause, two call
   sites, deliberately left alone here.

## Next work package

**P6A.** Not begun in this invocation.
