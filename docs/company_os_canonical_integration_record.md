# Canonical integration record: the curated candidate is now the baseline

**CEO-approved fast-forward integration.** `company-os-v1-bootstrap` advanced from
`b84f8a75a2d4aaeefd88798f23bc5948e7d39195` to
`9521de0e989baced6a88c2c5fa88fab719869808` by fast-forward only — no merge commit, no
rebase, no squash, no cherry-pick performed at integration time (all cherry-picking
happened earlier, building the candidate branch itself; see
`docs/company_os_canonical_integration_candidate.md`, carried forward unchanged in this
same tree). `main` was not touched: `8b1022aec899c7fa72ca77f2a1441c4d1b4ff48f`, before and
after.

## Before / after

| | SHA |
|---|---|
| Canonical before | `b84f8a75a2d4aaeefd88798f23bc5948e7d39195` |
| Candidate (approved source) | `9521de0e989baced6a88c2c5fa88fab719869808` |
| Canonical after | `9521de0e989baced6a88c2c5fa88fab719869808` (identical to the candidate — a fast-forward moves the pointer, it does not create a new commit) |
| `main` (untouched) | `8b1022aec899c7fa72ca77f2a1441c4d1b4ff48f` |

## Production-worthy changes integrated

1. CLI write-scope help text and 7 tests for the existing `--allow` path (`733b21e`) —
   no behavior change, closed a test/documentation gap.
2. `ManualExternalSessionAdapter.prepare` authority-source refactor (`3997a8e`) — the
   persisted and printed authority source can no longer drift from each other.
3. Receipt-prevalidation fix (`b12caa8`) — an evidence-format-only rejection no longer
   spends the developer's one attempt.
4. `developer_attempts_remaining` field on `EngineeringResult` (`7a594d28`).
5. Its null-safe correction (`532ce7a3`) — a present-but-`None` value round-trips through
   `to_dict`/`from_mapping` without raising, distinguishing a legacy record, an explicit
   zero, and a genuine unknown.
6. The section-header renumbering fix (`0bb362842fdac7f8419cb03df5ac9b5fd08e5df8`) that
   integrating 4 and 5 onto this lineage made necessary again.
7. Intake-classifier negation fix (`80a1ee6`) — a trigger term inside a clause that itself
   negates it (`"do not redesign the schema"`) no longer escalates a routine job to the
   specialist tier.

Full rationale, cherry-pick order, and per-commit classification: see
`docs/company_os_canonical_integration_candidate.md` (unchanged by this record).

## Intentionally excluded

- The rejected Job A implementation (`02828c0a`) — a real reviewer-caught defect;
  superseded by change 5 above, never picked.
- Two dogfood execution-trail commits (`834e7b1`, `a6da6dd`) — evidence/JSON only, no
  production code, left on their origin branches.
- **The intake-classifier coverage fix** (`12f7cf8`) and its evidence doc (`eadd066`) —
  real, reproduced content conflict against this same baseline's own independent
  `ebde582` fix in `company/engineering/intake.py`. Not resolved here (resolving is
  classifier-hardening work, explicitly out of scope for this integration). The
  coverage-fix branch remains pushed and available for a future, separately-scoped
  reconciliation pass.

## Test results (this exact integration, run before push)

| Suite | Result |
|---|---|
| `tests/test_company_engineering_execution.py` + runtime/transport | 216 passed |
| The gate's 11 required suites, run fresh | 789 passed, 0 failed |
| Integration gate, run with that evidence | exit 0, 34/34 required checks, 0 blockers |
| Full repository suite | **4693 passed, 6 failed, 337 skipped** |

The 6 failures are identical by name to an unmodified-canonical baseline run performed
during candidate preparation: `test_a_missing_godot_is_reported_rather_than_raised`,
`test_the_siting_tool_uses_the_scenes_own_edit_map`,
`test_the_projector_puts_each_node_in_the_frame_named_for_it`,
`test_every_authored_site_lands_in_at_least_one_frame`,
`test_the_analytic_parallax_finds_a_spread_in_every_chase`,
`test_the_geometric_parallax_field_is_identical_to_v251s` — pre-existing, gitignored
render-artifact absences, unrelated to any integrated change. **Zero new failures.**

## Verified before push, by direct diff inspection against the prior canonical tip

- `company/permissions.yaml` — byte-identical, no diff.
- `company/engineering/decision.py`, `company/engineering/work_order.py`,
  `company/integration/model.py` — untouched.
- `authorizes_merge` (on `EngineeringResult` and `CEODecision`) and
  `authorizes_production_integration` (on the gate's report model) — still hard-coded
  `False`, with construction-time refusal of any other value.
- `ai_platform/usage.py`, `company/finance/`, `tools/`, `knowledge/` — untouched.
- No Ctags/tree-sitter/Serena code anywhere in the integrated diff.
- No coverage-fix vocabulary (`"architecture change"`, `"approval policy"`,
  `"synchroniz"`, etc.) present in `company/engineering/intake.py` — confirming the
  exclusion held.

## Remaining autonomy blockers (unchanged, not addressed by this integration)

1. **Reserved/credential screening negation blindness** — `screen_reserved()`/
   `screen_credentials()` still match trigger terms without regard to negation.
2. **Authentication/migration classifier reference ambiguity** — bare single-word
   triggers can escalate a benign test/documentation mention.
3. **Deployment policy decision** — `"deploy"`/`"deployment"` maps to no specialist
   domain, reserved action, or routine-eligibility rule; undecided, not invented in code.
4. **Provider-usage event identifier design gap** — `ResourceUsageRecord` carries no
   stable identifier suitable for deduplication; no identifier invented, no schema
   changed.

None of these four were touched by this integration, per explicit instruction.

## Operating status after this integration

- **Canonical operating mode:** `SUPERVISED_REAL_ENGINEERING`.
- **Autonomy status:** `NOT_READY_FOR_ROUTINE_AUTONOMOUS_ENGINEERING` — unchanged.
- Routine autonomous engineering remains disabled. The CEO approval/integration gate
  remains mandatory. No production deployment behavior changed. No new engineering job
  was started by this integration.

See also (not reopened, not rewritten): `docs/company_os_canonical_integration_candidate.md`
(this tree), and, on `company-os-v1-supervised-burnin`,
`docs/company_os_autonomy_readiness_final.md`.
