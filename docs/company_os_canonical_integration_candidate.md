# Canonical integration candidate

**This is a curated candidate branch, not a merge.** It is not integrated into
`company-os-v1-bootstrap` or `main`, and this document does not authorize that — it
records what was inventoried, what was included and why, what was excluded and why, and
what was validated, so that decision can be made separately, later, by the CEO.

Base: `origin/company-os-v1-bootstrap` @ `b84f8a75a2d4aaeefd88798f23bc5948e7d39195`.

## Phase 2 — inventory

Checked every named lineage for ancestry against the current canonical tip first, so
nothing already-merged was re-proposed:

| Lineage | Already an ancestor of `company-os-v1-bootstrap`? |
|---|---|
| AI/resource-efficiency operational fixes (`company-os-v1-ai-efficiency`) | **yes** — already merged |
| `company-os-v1-consumer-resource-mode` | **yes** — already merged |
| `company-os-v1-repository-exploration-efficiency` (V1 + V2) | **yes** — already merged |
| `company-os-v1-read-efficiency-v3a` (+ V3B) | **yes** — already merged |
| `company-os-v1-external-runner-hardening` / `-external-engineering-runner` / `-engineering-execution` | **yes** — already merged |
| `company-os-v1-dogfood-receipt-prevalidation` | **no** — 5 unique commits, inventoried below |
| Job A implementation (`eng-legacy-attempts-remaining-default`) | no — rejected, excluded by CEO instruction |
| The correction (`eng-attempts-remaining-null-safe`) | no — inventoried below |
| Job B (`eng-test-section-header-renumber`) | no — inventoried below |
| `company-os-v1-intake-classifier-negation-fix` | no — inventoried below |
| `company-os-v1-intake-classifier-coverage-fix` | no — inventoried below |

**Canonical has moved independently since this investigation's supervised-burnin lineage
branched from it** (both descend from the same commit, `ba851fa`, read-efficiency-v3a).
Canonical's own later work includes `ebde582` ("routine eligibility guard for breaking
migration/schema/protocol work"), which **independently replaced the bare
`"migrate"`/`"migration"` architecture triggers with narrow, breaking-specific phrases**
— solving, on canonical, a case of the same general problem (a bare noun over-escalating)
that this investigation also found and partly addressed on a different branch. This
directly shaped Phase 3's outcome below.

### Classification of the 5 `company-os-v1-dogfood-receipt-prevalidation`-only commits

| Commit | What it is | Classification |
|---|---|---|
| `733b21e` | CLI help text + 7 tests for the existing `--allow` write-scope path (no behavior change, closes a test/doc gap) | **PRODUCTION_WORTHY** |
| `3997a8e` | `ManualExternalSessionAdapter.prepare` now shares one `authority_for` function with the no-outbox packet path, so the persisted and printed authority source cannot drift; 2 tests | **PRODUCTION_WORTHY** |
| `834e7b1` | Dogfood #1's full execution trail — `docs/` + evidence JSON only, no production code | **EXPERIMENT_ONLY** (evidence; stays on its origin branch, not pulled in) |
| `b12caa8` | An evidence-format-only receipt rejection no longer spends the developer attempt (`validate_receipt`, `ingest_developer_result`); 10 tests | **PRODUCTION_WORTHY** |
| `a6da6dd` | Dogfood #2's full execution trail — evidence JSON only, no production code | **EXPERIMENT_ONLY** (evidence; stays on its origin branch) |

### Classification of the burn-in-lineage implementation commits

| Commit | What it is | Classification |
|---|---|---|
| `7a594d28` (developer_attempts_remaining feature) | Adds the field, reviewed PASS, gate READY on Dogfood #2 | **PRODUCTION_WORTHY** |
| `02828c0a` (Job A) | Reviewer found a real defect (null-value round-trip crash); `changes_required` | **DO_NOT_INTEGRATE** — superseded by the correction below, per explicit CEO instruction |
| `532ce7a3` (the correction) | Fixes exactly Job A's finding; reviewer PASS, gate READY | **PRODUCTION_WORTHY** |
| `0bb362842fda` (Job B) | Comments-only section-banner renumbering; reviewer PASS, gate READY | **PRODUCTION_WORTHY** |
| `80a1ee6` (negation-fix) | Fixes a real false-positive in `derive_routing`; 158 targeted tests, full-suite regression clean | **PRODUCTION_WORTHY** |
| `da4f3ce` (negation-fix evidence doc) | Documents `80a1ee6` | **PRODUCTION_WORTHY** (documentation, travels with its fix) |
| `12f7cf8` (coverage-fix) | Fixes 3 real vocabulary gaps; 197 targeted tests, full-suite regression clean | **REQUIRES_POLICY_DECISION-adjacent, excluded this pass** — see Phase 3 |
| `eadd066` (coverage-fix evidence doc) | Documents `12f7cf8` | Excluded alongside `12f7cf8` — documents code not present in this candidate |

## Phase 3 — composition

Cherry-picked onto `company-os-v1-canonical-integration-candidate` (base
`company-os-v1-bootstrap`), in dependency order, verifying no history rewriting and
checking each one's necessity before picking it:

1. `733b21e` → `25d8c52` — clean, no conflicts.
2. `3997a8e` → `d03b991` — clean, no conflicts.
3. `b12caa8` → `93c6752` — clean auto-merge (`tests/test_company_engineering_execution.py`
   already carried canonical's own later additions; git's context merge composed both).
4. `7a594d28` → `d0d0d24` — clean auto-merge.
5. `532ce7a3` → `35f03a9` — clean auto-merge. **`02828c0a` was never cherry-picked at any
   point** — the correction was applied directly against the state left by step 4, exactly
   as it was originally built (on top of the burn-in branch's own post-rejection tip, not
   Job A's rejected commit).
6. `0bb362842fda` → `55f4040` — clean auto-merge. Verified necessary, not redundant: adding
   steps 4 and 5 onto canonical reintroduces the exact duplicate/out-of-order `# --- 15.`
   banner defect Job B was written to fix (canonical's file already had its own `# --- 15.`
   /`16.` sections before either cherry-pick landed), so this pick corrects a real
   duplication these very cherry-picks caused, not a stale one. Confirmed after the fact:
   banners `1`–`19` are unique and strictly increasing in the resulting file.
7. `80a1ee6` → `19fc8d8` — clean auto-merge, and verified by reading the result, not just
   trusting the absence of conflict markers: canonical's own `ebde582` vocabulary (the
   narrow migration/schema/protocol phrases) is untouched, and the new `_clauses`/
   `_escalates` helpers are correctly wired into `derive_routing` in place of the old
   `term in text` check for both `NOVEL_TRIGGERS` and `SPECIALIST_TRIGGERS` — the two
   independent changes to the same function composed correctly because they touch
   disjoint lines.
8. `da4f3ce` → `e230620` — clean, new file.

**`12f7cf8` (the coverage-fix) does NOT compose cleanly and was excluded, not forced.**
`git cherry-pick 12f7cf8` produces a real content conflict in
`company/engineering/intake.py`: canonical's `ebde582` and this investigation's coverage
fix each independently append different new phrases to the end of the same
`SPECIALIST_TRIGGERS["architecture"]` tuple. The two additions are not semantically
contradictory (both are valid, compatible phrases), but resolving the conflict means
hand-editing the trigger table's content — which is itself classifier-hardening work, and
this pass's own instructions explicitly rule that out. **Cherry-pick attempted, conflict
confirmed, aborted per the "stop and report" instruction rather than resolved.** The
coverage-fix branch remains valid, tested, and pushed on its own branch
(`company-os-v1-intake-classifier-coverage-fix` @ `eadd066`) for a future, dedicated
rebase pass to reconcile the two independent vocabulary extensions — not attempted here.

No benchmark-only artifacts, no experimental provider integrations, and no Job C
telemetry-schema changes are included, per instruction. Dependency order was preserved
throughout: nothing was picked before a commit it depends on.

## Phase 4 — validation

**Focused suites, each area:**

| Suite | Result |
|---|---|
| `tests/test_company_engineering_execution.py` | 180 passed |
| `tests/test_company_runtime.py` + `tests/test_company_execution_transport.py` + the above, combined | 216 passed |
| All other `test_company_*` suites | 1555 passed |
| The 11 suites the integration gate requires, run for real and supplied as
  `--suite-evidence` | 789 passed, 0 failed, individually matching the counts an
  independent prior gate run recorded for this same code state |

**Integration gate**, run for real with that suite evidence:
`python -m company.integration check --repo-root . --json --suite-evidence <file>` →
**exit code 0, 0 blockers, 34/34 required checks, `authorizes_production_integration:
false`** (as it always is, by the gate's own design — the CEO decides, the gate reports).
A bare run without suite evidence correctly reports the one expected `INSUFFICIENT_EVIDENCE`
blocker (`health.required_suites_pass`, "no reported run for..." three of the eleven
suites) — the gate cannot spawn pytest itself, by design, so this is the expected shape of
a run with no evidence supplied, not a defect.

**Full repository suite**, compared directly to a fresh checkout of unmodified canonical:

| | passed | failed | skipped |
|---|---:|---:|---:|
| Canonical baseline (`origin/company-os-v1-bootstrap`, unmodified) | 4654 | 6 | 337 |
| Integration candidate | 4693 | 6 | 337 |

Identical 6 failures by name on both
(`test_a_missing_godot_is_reported_rather_than_raised`,
`test_the_siting_tool_uses_the_scenes_own_edit_map`,
`test_the_projector_puts_each_node_in_the_frame_named_for_it`,
`test_every_authored_site_lands_in_at_least_one_frame`,
`test_the_analytic_parallax_finds_a_spread_in_every_chase`,
`test_the_geometric_parallax_field_is_identical_to_v251s` — pre-existing, gitignored
render-artifact absences, unrelated to any included change). The +39 passed is exactly the
new-test count across the 6 included commits. **Zero new regressions.**

**Other required confirmations**, checked by inspecting every included commit's diff, not
merely by running tests:

- Autonomous mode remains disabled — no included commit touches `permissions.yaml` or any
  `autonomy_levels` definition.
- No write authority widened — the included commits touch CLI help/tests, an authority-
  reporting refactor (not a grant), receipt/lifecycle handling, a CEO-facing report field,
  test comments, and routing-classifier matching. None changes what `may_write` a work
  order or packet can carry.
- CEO approval gate unchanged — no included commit touches `decision.py` or the
  `authorizes_merge`/`authorizes_production_integration` invariants (both remain hard-
  coded `False` wherever they already were).
- No provider-navigation tooling introduced — nothing here touches Serena, ctags,
  tree-sitter, or any code-navigation infrastructure.
- No unexpected model-tier escalation — the one classifier change included
  (`80a1ee6`) only *reduces* over-escalation (fixes a false positive); it adds no new
  escalation path beyond what its own 18 tests pin.
- No production-deployment behavior changed — the deployment policy gap (`"deploy"`/
  `"deployment"`) was left exactly as open as it already was; nothing here answers it.

## Phase 5 — supervised-operations readiness

Assessed for `SUPERVISED_REAL_ENGINEERING` only, **not** for autonomy readiness (a
separate, already-closed question — see
`docs/company_os_autonomy_readiness_final.md` on `company-os-v1-supervised-burnin`).

| Property | Status | Evidence |
|---|---|---|
| Deterministic intake | works | Unchanged mechanism; `80a1ee6` makes it more correct, not different in kind |
| Bounded write-grant | works | `733b21e`/`3997a8e` make the existing grant path *tested and correctly identified*, not new |
| Receipt prevalidation | works | `b12caa8`, in this candidate, tested (10 focused tests) |
| One-attempt policy | works | Unchanged; `developer_attempts_remaining` (this candidate) makes its *reporting* correct, not the policy itself |
| Independent review | works | Unchanged mechanism; proven in real use by burn-in Job A (not part of this candidate's code, but the mechanism this candidate's code runs inside) |
| Deterministic QA | works | Unchanged mechanism |
| Integration gate | works | Ran for real against this exact candidate, exit 0, 34/34, 0 blockers |
| CEO approval stop | works | Unchanged; `authorizes_merge`/`authorizes_production_integration` remain hard-coded `False` |
| External-runner telemetry | works | Unchanged mechanism; real telemetry already demonstrated across all four real jobs this investigation ran |
| No automatic continuation | works | Unchanged; nothing in this candidate touches the lifecycle's retry/continuation logic |

**This candidate is suitable for continued supervised real engineering.** It is not
assessed, and must not be read, as evidence toward autonomy readiness — that determination
is closed separately and remains `NOT_READY_FOR_ROUTINE_AUTONOMOUS_ENGINEERING`.

## Evidence

- This file: `docs/company_os_canonical_integration_candidate.md`
- Branch: `company-os-v1-canonical-integration-candidate`, base
  `b84f8a75a2d4aaeefd88798f23bc5948e7d39195`
- Included: `25d8c52`, `d03b991`, `93c6752`, `d0d0d24`, `35f03a9`, `55f4040`, `19fc8d8`,
  `e230620`
- Excluded, with reasons: `834e7b1`/`a6da6dd` (evidence, not code), `02828c0a` (rejected,
  superseded), `12f7cf8`/`eadd066` (real conflict with canonical's independent `ebde582`
  fix; resolving is classifier hardening, out of scope this pass)
